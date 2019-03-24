from .annotatedaudio import AnnotatedAudio
from .annotation import Annotation
from .audio import Audio

import numpy as np
import mir_eval
import os
from glob import glob
import warnings
from concurrent.futures import ThreadPoolExecutor
import multiprocessing

from collections import namedtuple

Track = namedtuple("Track", ("audio_path", "annot_path", "track_id"))

def melody_dataset_generator(dataset_audio_path, dataset_annot_path, audio_suffix=".wav", annot_suffix=".csv"):
    track_ids = [os.path.basename(f)[:-len(audio_suffix)] for f in sorted(glob(os.path.join(dataset_audio_path, "*"+audio_suffix)))]
    for track_id in track_ids:
        audio_path = glob(os.path.join(dataset_audio_path, track_id+audio_suffix))
        annot_path = glob(os.path.join(dataset_annot_path, track_id+annot_suffix))

        if len(annot_path) == 1:
            yield Track(audio_path[0], annot_path[0], track_id)
        else:
            if len(annot_path) == 0:
                pass
                # warnings.warn("Missing annotation for {}".format(track_id))
            else:
                warnings.warn("Multiple matching annotations for {}".format(track_id))


def load_melody_dataset(dataset_name, dataset_iterator):
    annotated_audios = []
    for audio_path, annot_path, track_id in dataset_iterator:
        uid = dataset_name+"_"+track_id
        # prepare audio
        audio = Audio(audio_path, uid)

        # prepare annotation
        annotation = None
        if annot_path is not None:
            annotation = (annot_path, uid)

        annotated_audios.append(AnnotatedAudio(annotation, audio))

    assert len(annotated_audios) > 0

    return annotated_audios


def parallel_preload(preload_fn, preload_data, threads=None):
    if threads is None:
        threads = multiprocessing.cpu_count()

    with ThreadPoolExecutor(max_workers=threads) as executor:
        executor.map(preload_fn, preload_data)

def melody_to_multif0(values):
    return [np.array([]) if x == 0 else np.array([x]) for x in values]


def multif0_to_melody(values):
    return np.array([0 if len(x) == 0 else x[0] for x in values])


def _hz_to_midi_safe(x):
    if x == 0:
        return 0
    elif x < 0:
        return -mir_eval.util.hz_to_midi(-x)
    else:
        return mir_eval.util.hz_to_midi(x)


hz_to_midi_safe = np.vectorize(_hz_to_midi_safe, otypes=[float])


def _midi_to_hz_safe(x):
    if x == 0:
        return 0
    elif x < 0:
        return -mir_eval.util.midi_to_hz(-x)
    else:
        return mir_eval.util.midi_to_hz(x)


midi_to_hz_safe = np.vectorize(_midi_to_hz_safe, otypes=[float])
