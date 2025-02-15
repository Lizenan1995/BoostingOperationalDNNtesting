

from __future__ import print_function


from scipy.misc import imsave

from driving_models import *
from utils import *
import numpy as np
np.random.seed(1)

# input image dimensions
img_rows, img_cols = 100, 100
input_shape = (img_rows, img_cols, 3)

# define input tensor as a placeholder
input_tensor = Input(shape=input_shape)

# load multiple models sharing same input tensor
model = Dave_orig(input_tensor=input_tensor, load_weights=True)
# model = Dave_norminit(input_tensor=input_tensor, load_weights=True)
# model = Dave_dropout(input_tensor=input_tensor, load_weights=True)

# ==============================================================================================
# start gen inputs
# img_paths = image.list_pictures('./testing/center', ext='jpg')


def load_data():
    path = './testing/final_example.csv'
    temp = np.loadtxt(path, delimiter=',', dtype=np.str, skiprows=(1))
    names = list(temp[:, 0])
    test = []
    label = []
    for i in range(len(names)):
        n = names[i]
        path = './testing/center/' + n + '.jpg'
        test.append(preprocess_image(path))
        label.append(float(temp[i, 1]))
    test = np.array(test)
    test = test.reshape(test.shape[0], 100, 100, 3)
    label = np.array(label)
    return test, label


def add_light(temp, gradients):
    import skimage
    temp = temp.reshape(temp.shape[0], -1)
    gradients = gradients.reshape(gradients.shape[0], -1)
    new_grads = np.ones_like(gradients)
    grad_mean = 500 * np.mean(gradients, axis=1)
    grad_mean = np.tile(grad_mean, temp.shape[1])
    grad_mean = grad_mean.reshape(temp.shape)
    temp = temp + 30 * new_grads * grad_mean
    temp = temp.reshape(temp.shape[0], 100, 100, 3)
    return temp



def build_neuron_tables(model, x_test):
    total_num = x_test.shape[0]
    # init dict and its input
    neuron_interval = defaultdict(np.array)
    neuron_proba = defaultdict(np.array)
    input_tensor = model.input
    layer = model.layers[-3]
    print(layer.output.shape)

    output = test_output
    lower_bound = np.min(output, axis=0)
    upper_bound = np.max(output, axis=0)

    for index in range(output.shape[-1]):
        # compute interval
        # temp = (upper_bound[index] - lower_bound[index]) * .25
        # let interval = 30
        interval = np.linspace(
            lower_bound[index], upper_bound[index], 20)
        neuron_interval[(layer.name, index)] = interval
        neuron_proba[(layer.name, index)] = output_to_interval(
            output[:, index], interval) / total_num

    return neuron_interval, neuron_proba


def build_testoutput(model, x_test):
    input_tensor = model.input
    layer = model.layers[-3]
    # get this layer's output
    output = layer.output
    output_fun = K.function([input_tensor], [output])
    output = output_fun([x_test])[0]
    output = output.reshape(output.shape[0], -1)
    test_output = output
    return test_output


def neuron_entropy(model, neuron_interval, neuron_proba, sample_index):
    total_num = sample_index.shape[0]
    if(total_num == 0):
        return -1e3
    neuron_entropy = []
    layer = model.layers[-3]
    output = test_output
    output = output[sample_index, :]
    # get lower and upper bound of neuron output
    # lower_bound = np.min(output, axis=0)
    # upper_bound = np.max(output, axis=0)
    for index in range(output.shape[-1]):
        # compute interval
        interval = neuron_interval[(layer.name, index)]
        bench_proba = neuron_proba[(layer.name, index)]
        test_proba = output_to_interval(
            output[:, index], interval) / total_num

        # cross entropy
        # test_proba = np.clip(test_proba, 1e-10, 1 - 1e-10)
        # log_proba = np.log(test_proba)
        # temp_proba = bench_proba.copy()
        # temp_proba[temp_proba < (.5 / total_num)] = 0
        # entropy = np.sum(log_proba * temp_proba)

        # KL divergence
        temp_proba1 = np.clip(test_proba, 1e-10, 1)
        temp_proba2 = np.clip(bench_proba, 1e-10, 1)

        entropy = np.sum(np.log(temp_proba2) * test_proba) - \
            np.sum(np.log(temp_proba1) * test_proba)

        neuron_entropy.append(entropy)
    return np.array(neuron_entropy)


def coverage(neuron_entropy):
    return np.mean(neuron_entropy)


def output_to_interval(output, interval):
    num = []
    for i in range(interval.shape[0] - 1):
        num.append(np.sum(np.logical_and(
            output >= interval[i], output < interval[i + 1])))
    return np.array(num)


def selectsample(model, x_test, y_test, delta, iterate):
    test = x_test
    arr = np.random.permutation(test.shape[0])
    batch = delta
    max_index0 = arr[0:30]
    min_index0 = arr[0:30]
    # max_index0 = np.array([]).astype('int')
    # min_index0 = np.array([]).astype('int')
    acc_list1 = []
    acc_list2 = []
    cov_random = []
    cov_select = []
    for i in range(iterate):
        arr = np.random.permutation(test.shape[0])
        max_coverage = -1e3
        min_coverage = 0
        max_index = -1
        min_index = -1
        max_iter = 30

        e = neuron_entropy(model, neuron_interval,
                           neuron_proba, max_index0)
        cov = coverage(e)
        max_coverage = cov

        # cov = -1e3
        # max_coverage = cov

        for j in range(max_iter):
            arr = np.random.permutation(test.shape[0])
            start = int(np.random.uniform(0, test.shape[0] - batch))
            temp_index = np.append(max_index0, arr[start:start + batch])
            e = neuron_entropy(model, neuron_interval,
                               neuron_proba, temp_index)
            new_coverage = coverage(e)
            if(new_coverage > max_coverage):
                max_coverage = new_coverage
                max_index = arr[start:start + batch]

        if(max_coverage == cov):
            start = int(np.random.uniform(0, test.shape[0] - batch))
            max_index = arr[start:start + batch]

        arr = np.random.permutation(test.shape[0])
        start = int(np.random.uniform(0, test.shape[0] - batch))
        min_index = arr[start:start + batch]

        max_index0 = np.append(max_index0, max_index)
        min_index0 = np.append(min_index0, min_index)

        # #
        e = neuron_entropy(model, neuron_interval,
                           neuron_proba, max_index0)
        cov1 = coverage(e)

        e = neuron_entropy(model, neuron_interval,
                           neuron_proba, min_index0)
        cov2 = coverage(e)

        cov_select.append(cov1)
        cov_random.append(cov2)
        print("current select coverage is {!s}".format(cov1))
        print("current random coverage is {!s}".format(cov2))
        label = y_test[max_index0]
        orig_sample = x_test[max_index0]
        orig_sample = orig_sample.reshape(-1, 100, 100, 3)
        pred = model.predict(orig_sample).reshape(-1)
        acc1 = np.sum(np.square(pred - label)) / orig_sample.shape[0]
        acc_list1.append(acc1)
        label = y_test[min_index0]
        orig_sample = x_test[min_index0]
        orig_sample = orig_sample.reshape(-1, 100, 100, 3)
        pred = model.predict(orig_sample).reshape(-1)
        acc2 = np.sum(np.square(pred - label)) / orig_sample.shape[0]
        acc_list2.append(acc2)
        print("numuber of samples is {!s}, select acc is {!s}, random acc is {!s}".format(
            orig_sample.shape[0], acc1, acc2))
    return acc_list1, acc_list2, cov_select, cov_random

def experiments(delta, iterate):
    pred = model.predict(x_test).reshape(-1)
    true_acc = np.sum(np.square(pred - y_test)) / x_test.shape[0]
    print("The final acc is {!s}".format(true_acc))

    acc_list1, acc_list2, cov1, cov2 = selectsample(
        model, x_test, y_test, delta, iterate)
    print("the select std is {!s}".format(
        np.mean(np.abs(acc_list1 - true_acc))))
    print("the random std is {!s}".format(
        np.mean(np.abs(acc_list2 - true_acc))))

    return np.array(acc_list1), np.array(acc_list2), np.array(cov1), np.array(cov2)


if __name__ == '__main__':
    # preprocess the data set
    test, label = load_data()
    x_test = test.copy()
    y_test = label.copy()
    img = deprocess_image(x_test[0])
    imsave('orig.png', img)
    temp = test.copy()
    pert = 1 * np.random.normal(size=x_test.shape)
    temp = add_light(temp, pert)
    img = deprocess_image(temp[0])
    imsave('pert.png', img)
    x_test = temp.copy()
    test = temp.copy()
    
    global test_output, neuron_interval, neuron_proba
    test_output = build_testoutput(model, x_test)
    neuron_interval, neuron_proba = build_neuron_tables(
        model, x_test)

    for k in range(50):
        print("the {} exp".format(k))
        acc1, acc2, cov1, cov2 = experiments(delta=5, iterate=30)
        np.savetxt('data/select{}.csv'.format(k), acc1)
        np.savetxt('data/random{}.csv'.format(k), acc2)
        np.savetxt('data/select_cov{}.csv'.format(k), cov1)
        np.savetxt('data/random_cov{}.csv'.format(k), cov2)
