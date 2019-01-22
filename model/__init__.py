from math import floor, ceil
import numpy as np

import tensorflow as tf

import mir_eval
mir_eval.multipitch.MIN_FREQ = 1

import matplotlib
import matplotlib.pyplot as plt
import visualization as vis

import time

import inspect
import os

import datasets
import pandas

from collections import defaultdict

class Network:
    def __init__(self, threads, seed=42):
        # Create an empty graph and a session
        graph = tf.Graph()
        graph.seed = seed

        gpu_options = tf.GPUOptions(allow_growth=True)
        self.session = tf.Session(graph = graph, config=tf.ConfigProto(gpu_options=gpu_options,
                                                                       inter_op_parallelism_threads=threads,
                                                                       intra_op_parallelism_threads=threads))

    def construct(self, args, create_model, output_types, output_shapes, create_summaries=None, dataset_preload_hook=None, dataset_transform=None):
        self.args = args
        self.logdir = args["logdir"]
        self.note_range = args["note_range"]

        self.samplerate = args["samplerate"]
        self.annotations_per_window = args["annotations_per_window"]
        self.frame_width = args["frame_width"]
        self.context_width = args["context_width"]
        self.window_size = self.annotations_per_window*self.frame_width + 2*self.context_width

        self.spectrogram_shape = None
        if "spectrogram_shape" in args:
            self.spectrogram_shape = args["spectrogram_shape"]

        self.dataset_preload_hook = dataset_preload_hook
        self.dataset_transform = dataset_transform

        # save the model function for easier reproducibility
        self.save_model_fnc(create_model)

        with self.session.graph.as_default():
            # Inputs
            self.handle = tf.placeholder(tf.string, shape=[])
            self.iterator = tf.data.Iterator.from_string_handle(self.handle, output_types, output_shapes)

            self.window_int16, self.annotations, self.times, self.audio_uid = self.iterator.get_next()

            self.window = tf.cast(self.window_int16, tf.float32)/32768.0

            # if self.spectrogram_shape is not None:
            #     self.spectrogram = tf.placeholder(tf.float32, [None, self.spectrogram_shape[0], self.spectrogram_shape[1]], name="spectrogram")

            self.is_training = tf.placeholder(tf.bool, [], name="is_training")

            # lowpriority TODO: použít booleanmask, abych pak nemusel odstraňovat ty nulové anotace
            self.ref_notes = tf.reduce_sum(tf.one_hot(self.annotations, self.note_range), axis=2)
            # sometimes there are identical notes in annotations (played by two different instruments)
            self.ref_notes = tf.cast(tf.greater(self.ref_notes, 0), tf.float32)
            # annotations are padded with zeros, so we manually remove this additional note
            dims = tf.shape(self.ref_notes)
            self.ref_notes = tf.concat([tf.zeros([dims[0], dims[1], 1]), self.ref_notes[:,:,1:]], axis=2)

            # create_model has to provide these values:
            self.est_notes = None
            self.loss = None
            self.training = None

            create_model(self, args)

            assert self.est_notes != None
            assert self.loss != None
            assert self.training != None

            self.saver = tf.train.Saver()

            summary_writer = tf.contrib.summary.create_file_writer(self.logdir, flush_millis=10 * 1000)

            self._summaries(args, summary_writer)

            if create_summaries:
                create_summaries(self, args, summary_writer)

            # Initialize variables
            self.session.run(tf.global_variables_initializer())
            with summary_writer.as_default():
                tf.contrib.summary.initialize(session=self.session, graph=self.session.graph)

            if os.path.exists(os.path.join(self.logdir, "model.ckpt")):
                self.restore()

    def _summaries(self, args, summary_writer):
        raise NotImplementedError()

    def train(self, train_dataset, valid_dataset, small_valid_dataset, epochs, eval_small_every_n_batches=3000, eval_every_n_batches=10000, save_every_n_batches=20000):
        with self.session.graph.as_default():
            train_iterator = train_dataset.dataset.make_initializable_iterator()
            validation_iterator = valid_dataset.dataset.make_initializable_iterator()
            small_validation_iterator = small_valid_dataset.dataset.make_initializable_iterator()

        train_iterator_handle = self.session.run(train_iterator.string_handle())
        validation_iterator_handle = self.session.run(validation_iterator.string_handle())
        small_validation_iterator_handle = self.session.run(small_validation_iterator.string_handle())

        b = 0
        timer = time.time()
        for i in range(epochs):
            self.session.run(train_iterator.initializer)
            print("=== epoch", i+1, "===")
            while True:
                feed_dict = {
                    self.handle: train_iterator_handle,
                    self.is_training: True
                }

                try:
                    accuracy, loss, _, _ = self.session.run([self.accuracy, self.loss, self.training, self.summaries["train"]], feed_dict)
                except tf.errors.OutOfRangeError:
                    break

                b += 1

                if b % 200 == 0:
                    print(".", end="")

                if b % 1000 == 0:
                    print("b {0}; t {1:.2f}; acc {2:.2f}; loss {3:.2f}".format(b, time.time() - timer, accuracy, loss))
                    timer = time.time()

                if b % eval_small_every_n_batches == 0:
                    self.session.run(small_validation_iterator.initializer)
                    oa, rpa, vr = self._evaluate_handle(small_valid_dataset, small_validation_iterator_handle, dataset_name="validation_small", visual_output=True)
                    print("small_validation: t {:.2f}, OA: {:.2f}, RPA: {:.2f}, VR: {:.2f}".format(time.time() - timer, oa, rpa, vr))
                    timer = time.time()

                if b % eval_every_n_batches == 0:
                    self.session.run(validation_iterator.initializer)
                    oa, rpa, vr = self._evaluate_handle(valid_dataset, validation_iterator_handle, dataset_name="validation")
                    print("validation: t {:.2f}, OA: {:.2f}, RPA: {:.2f}, VR: {:.2f}".format(time.time() - timer, oa, rpa, vr))
                    timer = time.time()

                if b % save_every_n_batches == 0:
                    self.save()
                    print("saving, t {:.2f}".format(time.time()-timer))
                    timer = time.time()
                
        print("=== done ===")

    def _predict_handle(self, handle):
        feed_dict = {
            self.is_training: False,
            self.handle: handle
        }

        notes = defaultdict(list)
        times = defaultdict(list)
        while True:
            try:
                fetches = self.session.run([self.est_notes, self.times, self.audio_uid], feed_dict)
            except tf.errors.OutOfRangeError:
                break

            # iterates through the batch output
            for est_notes_window, times_window, uid in zip(*fetches):
                uid = uid.decode("utf-8")
                # converts the sparse onehot/multihot vector to indices of ones
                # est_notes = [[i for i, v in enumerate(est_notes_frame) if v == 1] for est_notes_frame in est_notes_window]
                notes[uid].append(est_notes_window)
                # TODO zrychlit
                times[uid].append(times_window)

        estimations = {}
        for uid in notes.keys():
            est_time = np.concatenate(times[uid])
            est_notes = np.concatenate(notes[uid])
            est_freq = mir_eval.util.midi_to_hz(est_notes)
            est_freq[est_notes==0] = 0
            estimations[uid] = (est_time, est_freq)

        return estimations

    def predict(self, dataset_iterator, name="predict"):
        predict_data = datasets.load_melody_dataset(name, dataset_iterator)
        with self.session.graph.as_default():
            predict_dataset = datasets.AADataset(predict_data, self.args, self.dataset_preload_hook, self.dataset_transform)
            iterator = predict_dataset.dataset.make_one_shot_iterator()
        handle = self.session.run(iterator.string_handle())

        return self._predict_handle(handle)
    
    def _evaluate_handle(self, dataset, handle):
        raise NotImplementedError()

    def evaluate(self, dataset, **kwargs):
        with self.session.graph.as_default():
            iterator = dataset.dataset.make_one_shot_iterator()
        handle = self.session.run(iterator.string_handle())

        return self._evaluate_handle(dataset, handle, **kwargs)

    def save_model_fnc(self, create_model):
        plaintext = inspect.getsource(create_model)
        if not os.path.exists(self.logdir): os.mkdir(self.logdir)
        out = open(self.logdir+"/model_fnc.py", "a")
        out.write(plaintext)

    def save(self):
        save_path = self.saver.save(self.session, self.logdir+"/model.ckpt")
        print("Model saved in path:", save_path)
    def restore(self):
        self.saver.restore(self.session, self.logdir+"/model.ckpt")
        print("Model restored from path:", self.logdir)

class NetworkMelody(Network):
    def _summaries(self, args, summary_writer):
        # batch metrics
        with tf.name_scope("metrics"):
            # TODO: opravit, pořád nefunguje
            # ref_notes_b = tf.cast(self.ref_notes, tf.bool)
            # est_notes_b = tf.cast(self.est_notes, tf.bool)
            true_positive_sum = tf.constant(1, dtype=tf.int64)
            # true_positive_sum = tf.count_nonzero(tf.equal(self.ref_notes, self.est_notes))
            n_ref_sum = tf.count_nonzero(self.ref_notes != 0)
            n_est_sum = tf.count_nonzero(self.est_notes != 0)

            def safe_div(numerator, denominator):
                return tf.cond(denominator > 0, lambda: numerator/denominator, lambda: tf.constant(0, dtype=tf.float64))

            self.precision = safe_div(true_positive_sum, n_est_sum)
            self.recall = safe_div(true_positive_sum, n_ref_sum)
            acc_denom = n_est_sum + n_ref_sum - true_positive_sum
            self.accuracy = safe_div(true_positive_sum, acc_denom)

        self.summaries = {}
        with summary_writer.as_default(), tf.contrib.summary.record_summaries_every_n_global_steps(200):
            self.summaries["train"] = [tf.contrib.summary.scalar("train/loss", self.loss),
                                        tf.contrib.summary.scalar("train/precision", self.precision),
                                        tf.contrib.summary.scalar("train/recall", self.recall),
                                        tf.contrib.summary.scalar("train/accuracy", self.accuracy), ]

        with summary_writer.as_default(), tf.contrib.summary.always_record_summaries():
            # TODO vrátit given loss, případně pomocí metrics.mean
            # self.given_loss = tf.placeholder(tf.float32, [], name="given_loss")
            self.given_vr = tf.placeholder(tf.float32, [], name="given_vr")
            self.given_vfa = tf.placeholder(tf.float32, [], name="given_vfa")
            self.given_rpa = tf.placeholder(tf.float32, [], name="given_rpa")
            self.given_rca = tf.placeholder(tf.float32, [], name="given_rca")
            self.given_oa = tf.placeholder(tf.float32, [], name="given_oa")

            self.image1 = tf.placeholder(tf.uint8, [None, None, 4], name="image1")
            image1 = tf.expand_dims(self.image1, 0)

            self.summaries["validation_small"] = [tf.contrib.summary.image("validation_small/image1", image1),
                                            # tf.contrib.summary.scalar("validation_small/loss", self.given_loss),
                                            tf.contrib.summary.scalar("validation_small/voicing_recall", self.given_vr),
                                            tf.contrib.summary.scalar("validation_small/voicing_false_alarm", self.given_vfa),
                                            tf.contrib.summary.scalar("validation_small/raw_pitch_accuracy", self.given_rpa),
                                            tf.contrib.summary.scalar("validation_small/raw_chroma_accuracy", self.given_rca),
                                            tf.contrib.summary.scalar("validation_small/overall_accuracy", self.given_oa),
                                            ]

            self.summaries["validation"] = [
                                        # tf.contrib.summary.scalar("validation/loss", self.given_loss),
                                        tf.contrib.summary.scalar("validation/voicing_recall", self.given_vr),
                                        tf.contrib.summary.scalar("validation/voicing_false_alarm", self.given_vfa),
                                        tf.contrib.summary.scalar("validation/raw_pitch_accuracy", self.given_rpa),
                                        tf.contrib.summary.scalar("validation/raw_chroma_accuracy", self.given_rca),
                                        tf.contrib.summary.scalar("validation/overall_accuracy", self.given_oa),
                                        ]


    def _evaluate_handle(self, dataset, handle, dataset_name=None, visual_output=False, print_detailed=False):
        all_metrics = []
        reference = []
        estimation = []

        estimations = self._predict_handle(handle)

        for uid, (est_time, est_freq) in estimations.items():
            aa = dataset.get_annotated_audio_by_uid(uid)

            ref_time = np.array(aa.annotation.times)
            ref_freq = np.array(datasets.common.multif0_to_melody(aa.annotation.freqs))

            metrics = mir_eval.melody.evaluate(ref_time, ref_freq, est_time, est_freq)
            metrics["Track"] = uid
            all_metrics.append(metrics)

            if visual_output:
                reference += list(aa.annotation.notes)
                estimation += list(datasets.common.hz_to_midi_safe(est_freq))

        metrics = pandas.DataFrame(all_metrics).mean()

        if print_detailed:
            print(metrics)

        # write evaluation metrics to tf summary
        summaries = {
            self.given_vr: metrics['Voicing Recall'],
            self.given_vfa: metrics['Voicing False Alarm'],
            self.given_rpa: metrics['Raw Pitch Accuracy'],
            self.given_rca: metrics['Raw Chroma Accuracy'],
            self.given_oa: metrics['Overall Accuracy'],
        }

        if visual_output:
            title = "OA: {:.2f}, RPA: {:.2f}, RCA: {:.2f}, VR: {:.2f}, VFA: {:.2f}".format(
                metrics['Overall Accuracy'],
                metrics['Raw Pitch Accuracy'],
                metrics['Raw Chroma Accuracy'],
                metrics['Voicing Recall'],
                metrics['Voicing False Alarm']
                )
            
            estimation = datasets.common.melody_to_multif0(estimation)
            fig = vis.draw_notes(reference, estimation, title=title)
            summaries[self.image1] = vis.fig2data(fig)

            # suppress inline mode
            if not print_detailed:
                plt.close()

        if dataset_name is not None:
            self.session.run(self.summaries[dataset_name], summaries)

        return metrics['Overall Accuracy'], metrics['Raw Pitch Accuracy'], metrics['Voicing Recall']
