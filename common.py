import tensorflow as tf
import json
import datasets
import datetime


def get_medleydb_split():
    # For MDB and MDB synth we use the train/validation/test split according to deepsalience paper
    with open("data/MedleyDB/dataset_ismir_split.json") as f:
        medley_split = json.load(f)
    return medley_split


def prepare_medleydb(preload_fn):
    medley_split = get_medleydb_split()

    def mdb_split(name):
        gen = datasets.medleydb.generator("data/MedleyDB/MedleyDB/")
        return filter(lambda x: x.uid in medley_split[name], gen)

    train_data = datasets.load_melody_dataset(datasets.medleydb.prefix, mdb_split("train"))
    valid_data = datasets.load_melody_dataset(datasets.medleydb.prefix, mdb_split("validation"))

    for aa in train_data+valid_data:
        preload_fn(aa)

    small_validation_data = [
        valid_data[3].slice(15, 20.8),
        valid_data[9].slice(56, 61.4),
        valid_data[5].slice(55.6, 61.6),
    ]

    return train_data, valid_data, small_validation_data


def prepare_mdb_melody_synth(preload_fn):
    medley_split = get_medleydb_split()

    def mdb_split(name):
        gen = datasets.mdb_stem_synth.generator("data/MDB-melody-synth/")
        return filter(lambda x: x.uid in medley_split[name], gen)

    train_data = datasets.load_melody_dataset(datasets.mdb_melody_synth.prefix, mdb_split("train"))
    valid_data = datasets.load_melody_dataset(datasets.mdb_melody_synth.prefix, mdb_split("validation"))

    for aa in train_data+valid_data:
        preload_fn(aa)

    small_validation_data = [
        valid_data[3].slice(0, 40),
    ]

    return train_data, valid_data, small_validation_data


def prepare_mdb_stem_synth(preload_fn):
    medley_split = get_medleydb_split()

    def mdb_split(name):
        gen = datasets.mdb_stem_synth.generator("data/MDB-stem-synth/")
        return filter(lambda x: x.uid[:-len("_STEM_xx")] in medley_split[name], gen)

    train_data = datasets.load_melody_dataset(datasets.mdb_stem_synth.prefix, mdb_split("train"))
    valid_data = datasets.load_melody_dataset(datasets.mdb_stem_synth.prefix, mdb_split("validation"))

    for aa in train_data+valid_data:
        preload_fn(aa)

    small_validation_data = [
        valid_data[3].slice(30, 40),  # nějaká kytara
        valid_data[4].slice(38, 50),  # zpěv ženský
        valid_data[5].slice(55, 65),  # zpěv mužský
        valid_data[13].slice(130, 140),  # zpěv mužský
    ]

    return train_data, valid_data, small_validation_data


def name(args, prefix=""):
    name = "{}-{}-bs{}-apw{}-fw{}-ctx{}-nr{}-sr{}".format(
        prefix,
        datetime.datetime.now().strftime("%m-%d_%H%M%S"),
        args["batch_size"],
        args["annotations_per_window"],
        args["frame_width"],
        args["context_width"],
        args["note_range"],
        args["samplerate"],
    )
    args["logdir"] = "models/" + name

    return name


def bn_conv(inputs, filters, size, strides, padding, activation=None, dilation_rate=1, training=False):
    name = "bn_conv{}-f{}-s{}-dil{}-{}".format(size, filters, strides, dilation_rate, padding)
    with tf.name_scope(name):
        l = tf.layers.conv1d(inputs, filters, size, strides, padding, activation=None, use_bias=False, dilation_rate=dilation_rate)
        l = tf.layers.batch_normalization(l, training=training)
        if activation:
            return activation(l)
        else:
            return l


def conv(inputs, filters, size, strides, padding, activation=None, dilation_rate=1, training=False):
    name = "conv{}-f{}-s{}-dil{}-{}".format(size, filters, strides, dilation_rate, padding)
    return tf.layers.conv1d(inputs, filters, size, strides, padding, activation=activation, dilation_rate=dilation_rate, name=name)
