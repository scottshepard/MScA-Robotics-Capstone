#!/usr/bin/env python
# coding: utf-8

# In[15]:


import os
import sys
import struct
import math
import pickle
import audioop as ao
import numpy as np
import time
from datetime import datetime, date
from datetime import timedelta as td

import librosa
import wave
import pyaudio
from scipy.io.wavfile import write
from scipy.io import wavfile
import scipy.signal
from array import *

import soundfile as sf
import sounddevice as sd
from UrbanHMM import *
from UrbanHMM import UrbanHMMClassifier
#from UrbanAudio import *
#from UrbanAudio import UrbanHMMClassifier


# In[37]:


class Scavear:
    
    def __init__(self, model_dir, model_name, audio_path, log_dir='logs'):
        self.listener = Listener(audio_path=audio_path)
        # Audio Model
        self.model_dir = model_dir
        self.model_name = model_name
        with open(os.path.join(model_dir, model_name), 'rb') as model_file:
            self.model = pickle.load(model_file)
        # Log File
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        self.log_path = os.path.join(log_dir, 'log_'+str(date.today())+'.txt')

    def listen_record_classify_log(self, seconds=150):
        start = time.time()
        while time.time() - start < seconds:
            audio_clip_path, logtime = self.listener.listen_trigger_record(2, print_rms = True)
            #audio_clip_path = self.listener.record(2)
            filtered_audio_clip_path = self.listener.remove_noise(audio_clip_path)
            audio_class = self.classify(filtered_audio_clip_path)
            txt = ','.join([str(logtime), str(audio_class)])
            self.log(txt)
            print('Logged: ', txt)

    def classify(self, audio_file_path):
        return self.model.predict(audio_file_path, prediction_type = "labels")

    def log(self, txt):
        with open(self.log_path, 'a') as f:
            f.write(txt)
            f.write('\n')


# In[34]:


class Listener:

    @staticmethod
    def _stft(y, n_fft, hop_length, win_length):
        return librosa.stft(y=y, n_fft=n_fft, hop_length=hop_length, win_length=win_length)

    @staticmethod
    def _istft(y, hop_length, win_length):
        return librosa.istft(y, hop_length, win_length)

    @staticmethod
    def _amp_to_db(x):
        return librosa.core.amplitude_to_db(x, ref=1.0, amin=1e-20, top_db=80.0)

    @staticmethod
    def _db_to_amp(x,):
        return librosa.core.db_to_amplitude(x, ref=1.0)

    def __init__(self,
                 noise_path='noise',
                 audio_path='/home/pi/Desktop/scav_hunt/audio',
                 THRESHOLD = 3000,
                 SHORT_NORMALIZE = (1.0/32768.0),
                 CHUNK = 4096,
                 FORMAT = pyaudio.paInt16,
                 CHANNELS = 1,
                 RATE = 44100,
                 swidth = 2,
                 Max_Seconds = 10,
                 silence = True,
                 Time=0,
                 all_=[]):

        self.THRESHOLD = THRESHOLD
        self.SHORT_NORMALIZE = SHORT_NORMALIZE
        self.CHUNK = CHUNK
        self.FORMAT = FORMAT
        self.CHANNELS = CHANNELS
        self.RATE = RATE
        self.swidth = swidth
        self.Max_Seconds = Max_Seconds
        self.Time = Time
        self.all = all_
        self.audio_path = audio_path

        self.TimeoutSignal=int((RATE / CHUNK * Max_Seconds) + 2),

        self.noise_thresh = np.load(os.path.join(noise_path, 'noise_thresh.npy'))
        self.mean_freq_noise = np.load(os.path.join(noise_path, 'mean_freq.npy'))
        self.std_freq_noise = np.load(os.path.join(noise_path, 'std_freq.npy'))
        self.noise_stft_db = np.load(os.path.join(noise_path, 'noise_db.npy'))

    def remove_noise(
        self,
        audio_clip_path,
        n_grad_freq=2,
        n_grad_time=4,
        n_fft=2048,
        win_length=2048,
        hop_length=512,
        n_std_thresh=1.5,
        prop_decrease=1.0):
        
        rate, data = wavfile.read(audio_clip_path)
        audio_clip = data.astype(float)
        """Remove noise from audio based upon a clip containing only noise
        Args:
            audio_clip (array): The first parameter.
            noise_clip (array): The second parameter.
            n_grad_freq (int): how many frequency channels to smooth over with the mask.
            n_grad_time (int): how many time channels to smooth over with the mask.
            n_fft (int): number audio of frames between STFT columns.
            win_length (int): Each frame of audio is windowed by `window()`. The window will be of length `win_length` and then padded with zeros to match `n_fft`..
            hop_length (int):number audio of frames between STFT columns.
            n_std_thresh (int): how many standard deviations louder than the mean dB of the noise (at each frequency level) to be considered signal
            prop_decrease (float): To what extent should you decrease noise (1 = all, 0 = none)
            visual (bool): Whether to plot the steps of the algorithm
        Returns:
            array: The recovered signal with noise subtracted
        """
        noise_thresh = self.noise_thresh
        mean_freq_noise = self.mean_freq_noise
        std_freq_noise = self.std_freq_noise
        noise_stft_db = self.noise_stft_db        
        
        # STFT over signal
        sig_stft = self._stft(audio_clip, n_fft, hop_length, win_length)
        sig_stft_db = self._amp_to_db(np.abs(sig_stft))
        # Calculate value to mask dB to
        mask_gain_dB = np.min(self._amp_to_db(np.abs(sig_stft)))

        # Create a smoothing filter for the mask in time and frequency
        smoothing_filter = np.outer(
            np.concatenate(
                [
                    np.linspace(0, 1, n_grad_freq + 1, endpoint=False),
                    np.linspace(1, 0, n_grad_freq + 2),
                ]
            )[1:-1],
            np.concatenate(
                [
                    np.linspace(0, 1, n_grad_time + 1, endpoint=False),
                    np.linspace(1, 0, n_grad_time + 2),
                ]
            )[1:-1],
        )
        smoothing_filter = smoothing_filter / np.sum(smoothing_filter)
        # calculate the threshold for each frequency/time bin
        db_thresh = np.repeat(
            np.reshape(noise_thresh, [1, len(mean_freq_noise)]),
            np.shape(sig_stft_db)[1],
            axis=0,
        ).T
        # mask if the signal is above the threshold
        sig_mask = sig_stft_db < db_thresh
        # convolve the mask with a smoothing filter
        sig_mask = scipy.signal.fftconvolve(sig_mask, smoothing_filter, mode="same")
        sig_mask = sig_mask * prop_decrease
        # mask the signal
        sig_stft_db_masked = (
            sig_stft_db * (1 - sig_mask)
            + np.ones(np.shape(mask_gain_dB)) * mask_gain_dB * sig_mask
        )  # mask real
        sig_imag_masked = np.imag(sig_stft) * (1 - sig_mask)
        sig_stft_amp = (self._db_to_amp(sig_stft_db_masked) * np.sign(sig_stft)) + (
            1j * sig_imag_masked
        )
        # recover the signal
        recovered_signal = self._istft(sig_stft_amp, hop_length, win_length)
        recovered_spec = self._amp_to_db(
            np.abs(self._stft(recovered_signal, n_fft, hop_length, win_length))
        )
        
        newname = audio_clip_path.replace('.wav','')
        filtered_audio_clip_path = newname + '_filtered.wav'
        
        print(filtered_audio_clip_path)
        librosa.output.write_wav(filtered_audio_clip_path, recovered_signal, rate)
        #wavfile.write(filtered_audio_clip_path, rate, recovered_signal)
        
        return filtered_audio_clip_path

    def rms(self, frame, bytestream):
        count = len(frame)/self.swidth
        if (bytestream):
            fmt = "%dh"%(count)
            # short is 16 bit int
            frame = struct.unpack(fmt, frame)

        sum_squares = 0.0
        for sample in frame:
            n = sample * self.SHORT_NORMALIZE
            sum_squares += n*n
        # compute the rms
        rms = math.pow(sum_squares/count,0.5)
        return rms * 1000

    def filter_stream(self, stream):
        #convert bytestream to 16bit PCM
        sig = np.frombuffer(stream, dtype='<i2').reshape(-1, self.CHANNELS)
        # Change shape and type for noise removal function
        sig = sig.T[0].astype('float')
        #GoPiGo noise removal
        output = self.remove_noise(
            audio_clip=sig,
            n_std_thresh=2,
            prop_decrease=0.95)
        return(output)

    def open_stream(self):
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(
            format = self.FORMAT,
            channels = self.CHANNELS,
            rate = self.RATE,
            input = True,
            output = True,
            frames_per_buffer = self.CHUNK)
        return self.stream

    def close_stream(self):
        self.stream.stop_stream()
        self.stream.close()
        self.p.terminate()

    def listen(self, with_filter = False, print_rms=False):
        self.open_stream()
        print("listening now...")
        silence = True
        while silence:
            #try:
            #    input = self.stream.read(self.CHUNK)
            #except:
            #    continue
            
            input = self.stream.read(self.CHUNK)
            #data = int.from_bytes(input, byteorder='big', signed=True)
            if (with_filter):
                filtered = self.filter_stream(data)
                filtered_tuple = tuple(filtered)
                rms_value = self.rms(filtered_tuple, bytestream = False)
            else:
                #rms_value = self.rms(data, bytestream = False)
                rms_value = ao.rms(input,1)
                if print_rms:
                    print(rms_value)
                    
            if (rms_value > self.THRESHOLD):
                silence = False

    def listen_trigger_record(self, seconds, print_rms = False ):
        RECORD_SECONDS = seconds
        CHUNK = self.CHUNK
        CHANNELS = self.CHANNELS
        RATE = self.RATE
        FORMAT = self.FORMAT

        self.open_stream()
        print('listening...')
        frames = []
        rms_values = np.empty(1,dtype=float)
        while (True):
            trigger = self.stream.read(CHUNK)
            rms_value = int(ao.rms(trigger,2))
            rms_values = np.append(rms_values,rms_value)
            if(print_rms == True):
                print(rms_value)
            if (rms_value > self.THRESHOLD):
                frames.append(trigger)
                logtime = str(datetime.now())
                for i in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
                    data = self.stream.read(CHUNK)
                    frames.append(data)

                if not os.path.exists(self.audio_path):
                    os.makedirs(self.audio_path)

                filename = self.audio_path + '/' +                            'recording_' +                            format(datetime.now().strftime('%m%d%Y%H%M%S')) +                            '.wav'
                wf = wave.open(filename, 'wb')
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(self.p.get_sample_size(FORMAT))
                wf.setframerate(RATE)
                wf.writeframes(b''.join(frames))
                wf.close()
                self.close_stream()
                rms_filename = 'rms.txt' #+ \
                           #format(datetime.now().strftime('%m%d%Y%H%M%S')) + \
                           #'.txt'
                np.savetxt(rms_filename, rms_values, delimiter = ',')
                return filename, logtime
                
    def record(self, seconds):
        RECORD_SECONDS = seconds
        CHUNK = self.CHUNK
        CHANNELS = self.CHANNELS
        RATE = self.RATE
        FORMAT = self.FORMAT

        self.open_stream()
        frames = []
        for i in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
            data = self.stream.read(CHUNK)
            #convert bytestream to 16bit PCM
            #sig = np.frombuffer(data, dtype='<i2').reshape(-1, CHANNELS)
            # Change shape and type for noise removal function
            #sig = sig.T[0].astype('float')
            #GoPiGo noise removal
            #output = self.remove_noise(
            #    audio_clip=sig,
            #    n_std_thresh=2,
            #    prop_decrease=0.95)
            #prep for rms calcualtion
            #filtered_output = tuple(output)
            #RMS calculation
            #rms1 = self.rms(filtered_output, bytestream=False)
            # convert filtered numpy array back to a bytestream for saving..
            #new_sig = np.array([output.astype('int')],dtype='<u2').T
            #data = new_sig.tobytes()
            frames.append(data)

        if not os.path.exists(self.audio_path):
            os.makedirs(self.audio_path)

        filename = self.audio_path + '/' +                    'recording_' +                    format(datetime.now().strftime('%m%d%Y%H%M%S')) +                    '.wav'
        wf = wave.open(filename, 'wb')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(self.p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))
        wf.close()
        self.close_stream()
        return filename


# In[35]:


if __name__ == '__main__':
    from datetime import date

    today = str(date.today())

    ear = Scavear(
        model_dir='models/audio',
        model_name='hmm_cvbest_f1_56437703.pkl',
        audio_path='data/audio/{}'.format(today)
    )
    ear.listen_record_classify_log()


# In[36]:


#import matplotlib.pyplot as plt

#rms_value = np.loadtxt(fname = "rms.txt", dtype=int)
#plt.plot(rms_value)

