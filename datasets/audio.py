import os
import numpy as np
from resampy import resample
import soundfile as sf

def check_dir(path):
    if not os.path.isdir(path):
        os.makedirs(path)

PROCESSED_FILES_PATH = "./processed"

''' Audio container
Audio can be represented in different forms - as raw audio with various
sampling rates or as spectrograms. '''
class Audio:
    def __init__(self, path, uid):
        self.path = path
        self.filename = os.path.splitext(os.path.basename(path))[0]
        self.uid = uid
        self.samples = []
        self.samples_count = 0
        self.samplerate = 0
        self.spectrogram_hop_size = None
        self.spectrogram = None

    def load_resampled_audio(self, samplerate):
        assert self.samples == []

        check_dir(PROCESSED_FILES_PATH)
        resampled_path = os.path.join(PROCESSED_FILES_PATH, self.uid+"_{}.wav".format(samplerate))

        if not os.path.isfile(resampled_path):
            audio, sr_orig = sf.read(self.path)
            if sr_orig == samplerate:
                resampled_path = self.path
            else:
                print("resampling", self.uid, "shape", audio.shape)
                if len(audio.shape) >= 2:  # mono downmixing, if needed
                    audio = np.mean(audio, axis=1)
                audio_low = resample(audio, sr_orig, samplerate)

                sf.write(resampled_path, audio_low.astype(np.float32), samplerate)

        audio, sr_orig = sf.read(resampled_path, dtype="int16")
        self.samples = audio

        assert sr_orig == samplerate

        self.samples_count = len(self.samples)
        self.samplerate = samplerate

    def load_spectrogram(self, spec_function, spec_function_thumbprint, hop_size):
        self.spectrogram_hop_size = hop_size

        check_dir(PROCESSED_FILES_PATH)
        spec_path = os.path.join(PROCESSED_FILES_PATH, self.uid+"_{}.npy".format(spec_function_thumbprint))

        # spec_path = self.path.replace(".wav", spec_function_thumbprint+".npy")
        audio, samplerate = sf.read(self.path)

        if os.path.isfile(spec_path):
            spec = np.load(spec_path)
        else:
            spec = spec_function(audio, samplerate)
            np.save(spec_path, spec)

        self.spectrogram = spec
        self.samples_count = len(audio)
        self.samplerate = samplerate

    def get_duration(self):
        if self.samplerate == 0:
            return 0
        return self.samples_count/self.samplerate

    def get_padded_audio(self, start_sample, end_sample):
        if len(self.samples) == 0:
            return None

        cut_start = start_sample
        cut_end = end_sample

        last_sample_index = self.samples_count - 1

        if start_sample > last_sample_index:
            return np.zeros(end_sample-start_sample, dtype=np.int16)

        # padding the snippets with zeros when the context reaches outside the audio
        cut_start_diff = 0
        cut_end_diff = 0
        if start_sample < 0:
            cut_start = 0
            cut_start_diff = cut_start - start_sample
        if end_sample > last_sample_index:
            cut_end = last_sample_index
            cut_end_diff = end_sample - last_sample_index

        audio = self.samples[cut_start:cut_end]

        if cut_start_diff:
            zeros = np.zeros(cut_start_diff, dtype=np.int16)
            audio = np.concatenate([zeros, audio])

        if cut_end_diff:
            zeros = np.zeros(cut_end_diff, dtype=np.int16)
            audio = np.concatenate([audio, zeros])
        return audio

    def get_padded_spectrogram(self, start_sample, end_sample):
        if self.spectrogram is None:
            return None

        cut_length = int((end_sample - start_sample)/self.spectrogram_hop_size)

        cut_start = start_window = int(start_sample/self.spectrogram_hop_size)
        cut_end = end_window = cut_start + cut_length

        last_window_index = self.spectrogram.shape[1] - 1

        # padding the snippets with zeros when the context reaches outside the audio
        cut_start_diff = 0
        cut_end_diff = 0
        if start_window < 0:
            cut_start = 0
            cut_start_diff = cut_start - start_window
        if end_window > last_window_index:
            cut_end = last_window_index
            cut_end_diff = end_window - last_window_index

        spectrogram = self.spectrogram[:, cut_start:cut_end]

        if cut_start_diff:
            zeros = np.zeros(self.spectrogram.shape[:1]+(cut_start_diff,), dtype=self.spectrogram.dtype)
            spectrogram = np.concatenate([zeros, spectrogram], axis=1)

        if cut_end_diff:
            zeros = np.zeros(self.spectrogram.shape[:1]+(cut_end_diff,), dtype=self.spectrogram.dtype)
            spectrogram = np.concatenate([spectrogram, zeros], axis=1)

        return spectrogram

    def slice(self, start, end):
        if len(self.samples) == 0:
            raise Exception("Audio samples are empty")

        sliced = Audio(self.path, self.uid)
        sliced.samplerate = self.samplerate
        b0, b1 = int(start*self.samplerate), int(end*self.samplerate)
        sliced.samples = self.samples[b0:b1]

        if len(sliced.samples) == 0:
            raise Exception("Sliced audio samples are empty")

        sliced.samples_count = b1-b0

        if self.spectrogram is not None:
            sliced.spectrogram_hop_size = self.spectrogram_hop_size
            sliced.spectrogram = self.spectrogram[:, int(b0/self.spectrogram_hop_size):int(b1/self.spectrogram_hop_size)]

        return sliced

    def get_window_at_sample(self, window_start_sample, inner_window_size, context_width):
        window_end_sample = window_start_sample + inner_window_size

        b0 = int(window_start_sample-context_width)
        b1 = int(window_end_sample+context_width)

        return self.get_padded_audio(b0, b1), self.get_padded_spectrogram(b0, b1)

    def iterator(self, inner_window_size, context_width):
        for sample_index in range(0, self.samples_count, inner_window_size):
            yield self.get_window_at_sample(sample_index, inner_window_size, context_width)
