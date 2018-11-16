import os
from abc import ABC
from functools import reduce

import numpy as np
import torch
from sklearn.model_selection import train_test_split

from autokeras.constant import Constant
from autokeras.nn.loss_function import classification_loss, regression_loss
from autokeras.nn.metric import Accuracy, MSE
from autokeras.preprocessor import OneHotEncoder, TextDataTransformer
from autokeras.supervised import DeepSupervised
from autokeras.text.text_preprocessor import text_preprocess
from autokeras.utils import pickle_to_file, validate_xy


class TextSupervised(DeepSupervised, ABC):
    """TextClassifier class.

    Attributes:
        cnn: CNN module from net_module.py.
        path: A path to the directory to save the classifier as well as intermediate results.
        y_encoder: Label encoder, used in transform_y or inverse_transform_y for encode the label. For example,
                    if one hot encoder needed, y_encoder can be OneHotEncoder.
        data_transformer: A transformer class to process the data. See example as ImageDataTransformer.
        verbose: A boolean value indicating the verbosity mode which determines whether the search process
                will be printed to stdout.
    """

    def __init__(self, **kwargs):
        """Initialize the instance.

        The classifier will be loaded from the files in 'path' if parameter 'resume' is True.
        Otherwise it would create a new one.
        Args:
            verbose: A boolean of whether the search process will be printed to stdout.
            path: A string. The path to a directory, where the intermediate results are saved.
            resume: A boolean. If True, the classifier will continue to previous work saved in path.
                Otherwise, the classifier will start a new search.
            searcher_args: A dictionary containing the parameters for the searcher's __init__ function.
        """
        super().__init__(**kwargs)

    def fit(self, x, y, x_test=None, y_test=None, batch_size=None, time_limit=None):
        """Find the best neural architecture and train it.

        Based on the given dataset, the function will find the best neural architecture for it.
        The dataset is in numpy.ndarray format.
        So they training data should be passed through `x_train`, `y_train`.

        Args:
            x: A numpy.ndarray instance containing the training data.
            y: A numpy.ndarray instance containing the label of the training data.
            y_test: A numpy.ndarray instance containing the testing data.
            x_test: A numpy.ndarray instance containing the label of the testing data.
            batch_size: int, define the batch size.
            time_limit: The time limit for the search in seconds.
        """
        x = text_preprocess(x, path=self.path)

        x = np.array(x)
        y = np.array(y).flatten()

        super().fit(x, y, x_test, y_test, time_limit)

    def init_transformer(self, x):
        # Wrap the data into DataLoaders
        if self.data_transformer is None:
            self.data_transformer = TextDataTransformer()

    def final_fit(self, x_train=None, y_train=None, x_test=None, y_test=None, trainer_args=None, retrain=False):
        """Final training after found the best architecture.

        Args:
            x_train: A numpy.ndarray of training data.
            y_train: A numpy.ndarray of training targets.
            x_test: A numpy.ndarray of testing data.
            y_test: A numpy.ndarray of testing targets.
            trainer_args: A dictionary containing the parameters of the ModelTrainer constructor.
            retrain: A boolean of whether reinitialize the weights of the model.
        """
        x_train = text_preprocess(x_train, path=self.path)
        if x_test is not None:
            x_test = text_preprocess(x_test, path=self.path)

        if trainer_args is None:
            trainer_args = {'max_no_improvement_num': 30}

        y_train = self.transform_y(y_train)
        y_test = self.transform_y(y_test)

        train_data = self.data_transformer.transform_train(x_train, y_train)
        test_data = self.data_transformer.transform_test(x_test, y_test)

        self.cnn.final_fit(train_data, test_data, trainer_args, retrain)

    def predict(self, x_test):
        """Return predict results for the testing data.

        Args:
            x_test: An instance of numpy.ndarray containing the testing data.

        Returns:
            A numpy.ndarray containing the results.
        """
        if Constant.LIMIT_MEMORY:
            pass
        test_loader = self.data_transformer.transform_test(x_test)
        model = self.cnn.best_model.produce_model()
        model.eval()

        outputs = []
        with torch.no_grad():
            for index, inputs in enumerate(test_loader):
                outputs.append(model(inputs).numpy())
        output = reduce(lambda x, y: np.concatenate((x, y)), outputs)
        return self.inverse_transform_y(output)

    def evaluate(self, x_test, y_test):
        x_test = text_preprocess(x_test, path=self.path)
        """Return the accuracy score between predict value and `y_test`."""
        y_predict = self.predict(x_test)
        return self.metric().evaluate(y_test, y_predict)


class TextClassifier(TextSupervised):
    @property
    def metric(self):
        return Accuracy

    @property
    def loss(self):
        return classification_loss

    def transform_y(self, y_train):
        # Transform y_train.
        if self.y_encoder is None:
            self.y_encoder = OneHotEncoder()
            self.y_encoder.fit(y_train)
        y_train = self.y_encoder.transform(y_train)
        return y_train

    def inverse_transform_y(self, output):
        return self.y_encoder.inverse_transform(output)

    def get_n_output_node(self):
        return self.y_encoder.n_classes


class TextRegressor(TextClassifier):
    """ TextRegressor class.

    It is used for text regression. It searches convolutional neural network architectures
    for the best configuration for the text dataset.
    """

    @property
    def loss(self):
        return regression_loss

    @property
    def metric(self):
        return MSE

    def get_n_output_node(self):
        return 1

    def transform_y(self, y_train):
        return y_train.flatten().reshape(len(y_train), 1)

    def inverse_transform_y(self, output):
        return output.flatten()
