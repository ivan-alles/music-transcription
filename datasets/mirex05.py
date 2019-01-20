
import os
from .common import mirex_melody_dataset_generator, load_melody_dataset

def generator(dataset_root):
    dataset_audio_path = os.path.join(dataset_root, "mirex05TrainFiles")
    dataset_annot_path = os.path.join(dataset_root, "mirex05TrainFiles")

    return mirex_melody_dataset_generator(dataset_audio_path, dataset_annot_path, annot_extension="REF.txt")

def dataset(dataset_root):
    return load_melody_dataset("mirex05", generator(dataset_root))
