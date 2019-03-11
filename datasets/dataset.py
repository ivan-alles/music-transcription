import numpy as np
import os
import librosa
import tensorflow as tf

import datasets

from .annotatedaudio import AnnotatedAudio
from .annotation import Annotation
from .audio import Audio

np.random.seed(42)

class AADataset:
    def __init__(self, _annotated_audios, args, dataset_transform=None, shuffle=False, hop_size=None):
        self._annotated_audios = _annotated_audios

        # self.frame_width = int(np.round(aa.annotation.get_frame_width()*self.samplerate))
        self.frame_width = args.frame_width

        self.context_width = args.context_width
        self.annotations_per_window = args.annotations_per_window
        self.hop_size = hop_size if hop_size is not None else self.annotations_per_window
        # todo: přejmenovat na window_width?
        self.inner_window_size = self.annotations_per_window*self.frame_width
        self.window_size = self.inner_window_size + 2*self.context_width

        for aa in self._annotated_audios:
            if aa.annotation is None:
                # add dummy annotation if the annotation is missing
                times = np.arange(0, aa.audio.samples_count, self.frame_width) / aa.audio.samplerate
                freqs = np.tile(440, [len(times),1])
                notes = np.tile(69, [len(times),1])

                aa.annotation = Annotation(times, freqs, notes)

        self.samplerate = _annotated_audios[0].audio.samplerate

        # generate example positions all at once so that we can shuffle them as a whole
        indices = []
        for aa_index, aa in enumerate(self._annotated_audios):
            if self.window_size > aa.audio.samples_count:
                raise RuntimeError("Window size is bigger than the audio.")

            annot_length = len(aa.annotation.times)
            annotation_indices = np.arange(0, annot_length, self.hop_size, dtype=np.int32)
            aa_indices = np.full((len(annotation_indices),), aa_index, dtype=np.int32)

            indices.append(np.stack((aa_indices, annotation_indices), axis=-1))
        indices = np.concatenate(indices)
        
        if shuffle:
            indices = np.random.permutation(indices)

        index_dataset = tf.data.Dataset.from_tensor_slices((indices.T[0], indices.T[1]))

        self.dataset = index_dataset if dataset_transform is None else index_dataset.apply(lambda tf_dataset: dataset_transform(tf_dataset, self))

        print("dataset id:", _annotated_audios[0].audio.uid.split("_")[0])
        print("dataset duration: {:.2f} minutes".format(self.total_duration/60))
        print("dataset examples:", self.total_examples)
        self.max_polyphony = np.max([aa.annotation.max_polyphony for aa in self._annotated_audios])
        print("max. polyphony:", self.max_polyphony)
        if self.annotations_per_window != self.hop_size:
            print("using hop_size", self.hop_size)
        print()

    def prepare_example(self, aa_index_op, annotation_index_op):
        output_types, output_shapes = zip(*[
            (tf.int16,   tf.TensorShape([self.window_size])),
            (tf.float32, tf.TensorShape([self.annotations_per_window, None])),
            (tf.float32, tf.TensorShape([self.annotations_per_window])),
            (tf.string,  None),
        ])
        outputs = tf.py_func(self._create_example, [aa_index_op, annotation_index_op], output_types)
        for output, shape in zip(outputs, output_shapes):
            output.set_shape(shape)
        return outputs
    
    def is_example_voiced(self, window_op, annotations_op, times_op, audio_uid_op):
        return tf.equal(tf.count_nonzero(tf.equal(annotations_op, 0)), 0)
    
    def mix_example_with(self, audio):
        def _mix_example(window_op, annotations_op, times_op, audio_uid_op):
            output_types, output_shapes = zip(*[
                (tf.int16,   tf.TensorShape([self.window_size])),
                (tf.float32, tf.TensorShape([self.annotations_per_window, None])),
                (tf.float32, tf.TensorShape([self.annotations_per_window])),
                (tf.string,  None),
            ])

            def mix_with(window, annotations, times, audio_uid):
                window = (window + audio[:len(window)])//2
                return (window, annotations, times, audio_uid)

            outputs = tf.py_func(mix_with, [window_op, annotations_op, times_op, audio_uid_op], output_types)
            for output, shape in zip(outputs, output_shapes):
                output.set_shape(shape)
            return outputs
        return _mix_example
    
    @property
    def total_duration(self):
        return sum([aa.annotation.times[-1] for aa in self._annotated_audios])
    
    @property
    def total_examples(self):
        return sum([len(aa.annotation.times)//self.annotations_per_window for aa in self._annotated_audios])

    def all_samples(self):
        samples = [aa.audio.samples for aa in self._annotated_audios]
        return np.concatenate(samples)

    def _create_example(self, aa_index, annotation_start):
        aa = self._annotated_audios[aa_index]

        annotation_end = min(len(aa.annotation.times), annotation_start + self.annotations_per_window)
        
        annotations = aa.annotation.notes[annotation_start:annotation_end]
        times = aa.annotation.times[annotation_start:annotation_end]

        len_diff = self.annotations_per_window - (annotation_end - annotation_start)
        if len_diff > 0:
            times = np.pad(times, (0, len_diff), "constant")
            annotations = np.pad(annotations, ((0, len_diff),(0,0)), "constant")

        window_start_sample = np.floor(times[0]*self.samplerate)
        audio, spectrogram = aa.audio.get_window_at_sample(window_start_sample, self.inner_window_size, self.context_width)

        return (audio, annotations, times, aa.audio.uid)

    def get_annotated_audio_by_uid(self, uid):
        for aa in self._annotated_audios:
            if aa.audio.uid == uid:
                return aa
