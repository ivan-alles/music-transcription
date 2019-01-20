import os
from .common import mirex_melody_dataset_generator, load_melody_dataset

prefix = "adc04"

def generator(dataset_root):
    dataset_audio_path = os.path.join(dataset_root, "adc2004_full_set")
    dataset_annot_path = os.path.join(dataset_root, "adc2004_full_set")

    return mirex_melody_dataset_generator(dataset_audio_path, dataset_annot_path, annot_extension="REF.txt")

def dataset(dataset_root):
    return load_melody_dataset(prefix, generator(dataset_root))
