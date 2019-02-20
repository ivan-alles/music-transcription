import tensorflow as tf
import json
import datasets
import datetime
from model import VD, VisualOutputHook, MetricsHook, MetricsHook_mf0, VisualOutputHook_mf0, SaveBestModelHook

def name(args, prefix=""):
    if "logdir" not in args:
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

        print()
        print(name)
        print()


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


def all_datasets(args, preload_fn, dataset_transform, dataset_transform_train):
    wjazzd_train, wjazzd_validation, wjazzd_small_validation = datasets.wjazzd.prepare(preload_fn)
    wjazzd_validation_dataset = datasets.AADataset(wjazzd_validation, args, dataset_transform)
    wjazzd_small_validation_dataset = datasets.AADataset(wjazzd_small_validation, args, dataset_transform)

    medleydb_train, medleydb_validation, medleydb_small_validation = datasets.medleydb.prepare(preload_fn)
    medleydb_validation_dataset = datasets.AADataset(medleydb_validation, args, dataset_transform)
    medleydb_small_validation_dataset = datasets.AADataset(medleydb_small_validation, args, dataset_transform)

    mdb_melody_synth_train, mdb_melody_synth_validation, _ = datasets.mdb_melody_synth.prepare(preload_fn)
    mdb_melody_synth_validation_dataset = datasets.AADataset(mdb_melody_synth_validation, args, dataset_transform)

    mdb_stem_synth_train, _, mdb_stem_synth_small_validation = datasets.mdb_stem_synth.prepare(preload_fn)
    mdb_stem_synth_small_validation_dataset = datasets.AADataset(mdb_stem_synth_small_validation, args, dataset_transform)

    _, _, mdb_mf0_synth_small_validation = datasets.mdb_mf0_synth.prepare(preload_fn)
    mdb_mf0_synth_small_validation_dataset = datasets.AADataset(mdb_mf0_synth_small_validation, args, dataset_transform)

    train_dataset = datasets.AADataset(medleydb_train+wjazzd_train+mdb_stem_synth_train+mdb_melody_synth_train, args, dataset_transform_train, shuffle=True)

    small_hooks_mf0 = [MetricsHook_mf0(), VisualOutputHook_mf0(True, True, True)]
    small_hooks = [MetricsHook(), VisualOutputHook(True, True, False)]
    valid_hooks = [MetricsHook(), VisualOutputHook(False, False, True)]
    validation_datasets=[
        VD("small_"+datasets.mdb_mf0_synth.prefix, mdb_mf0_synth_small_validation_dataset, 3000, small_hooks_mf0),
        VD("small_"+datasets.mdb_stem_synth.prefix, mdb_stem_synth_small_validation_dataset, 3000, small_hooks),
        VD("small_"+datasets.medleydb.prefix, medleydb_small_validation_dataset, 3000, small_hooks),
        VD("small_"+datasets.wjazzd.prefix, wjazzd_small_validation_dataset, 3000, small_hooks),
        VD(datasets.medleydb.prefix, medleydb_validation_dataset, 20000, valid_hooks),
        VD(datasets.mdb_melody_synth.prefix, mdb_melody_synth_validation_dataset, 30000, valid_hooks),
        VD(datasets.wjazzd.prefix, wjazzd_validation_dataset, 30000, valid_hooks),
    ]

    return train_dataset, validation_datasets


def mdb_datasets(args, preload_fn, dataset_transform, dataset_transform_train):
    medleydb_train, medleydb_validation, medleydb_small_validation = datasets.medleydb.prepare(preload_fn)
    medleydb_validation_dataset = datasets.AADataset(medleydb_validation, args, dataset_transform)
    medleydb_small_validation_dataset = datasets.AADataset(medleydb_small_validation, args, dataset_transform)

    train_dataset = datasets.AADataset(medleydb_train, args, dataset_transform_train, shuffle=True)

    validation_datasets = [
        VD("small_"+datasets.medleydb.prefix, medleydb_small_validation_dataset, 3000, [
            MetricsHook(),
            VisualOutputHook(True, True, False)
            ]),
        VD(datasets.medleydb.prefix, medleydb_validation_dataset, 20000, [
            MetricsHook(),
            VisualOutputHook(False, False, True),
            SaveBestModelHook()
            ]),
    ]

    return train_dataset, validation_datasets
