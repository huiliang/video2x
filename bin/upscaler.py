#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Name: Video2X Upscaler
Author: K4YT3X
Date Created: December 10, 2018
Last Modified: March 4, 2019

Licensed under the GNU General Public License Version 3 (GNU GPL v3),
    available at: https://www.gnu.org/licenses/gpl-3.0.txt

(C) 2018-2019 K4YT3X
"""

from avalon_framework import Avalon
from exceptions import *
from ffmpeg import Ffmpeg
from fractions import Fraction
from tqdm import tqdm
from waifu2x_caffe import Waifu2xCaffe
from waifu2x_converter import Waifu2xConverter
import os
import re
import shutil
import tempfile
import threading
import time

MODELS_AVAILABLE = ['upconv_7_anime_style_art_rgb', 'upconv_7_photo', 'anime_style_art_rgb', 'photo',
                    'anime_style_art_y', 'upresnet10', 'cunet']


class Upscaler:

    def __init__(self, input_video, output_video, method, waifu2x_path, ffmpeg_path, waifu2x_driver='waifu2x_caffe', ffmpeg_arguments=[], ffmpeg_hwaccel='auto', output_width=False, output_height=False, ratio=False, model_type='anime_style_art_rgb', threads=3, video2x_cache_folder='{}\\video2x'.format(tempfile.gettempdir()), preserve_frames=False):
        # Mandatory arguments
        self.input_video = input_video
        self.output_video = output_video
        self.method = method
        self.waifu2x_path = waifu2x_path
        self.ffmpeg_path = ffmpeg_path
        self.waifu2x_driver = waifu2x_driver

        # Check sanity of waifu2x_driver option
        if waifu2x_driver != 'waifu2x_caffe' and waifu2x_driver != 'waifu2x_converter':
            raise Exception('Unrecognized waifu2x driver: {}'.format(waifu2x_driver))

        # Optional arguments
        self.ffmpeg_arguments = ffmpeg_arguments
        self.ffmpeg_hwaccel = ffmpeg_hwaccel
        self.output_width = output_width
        self.output_height = output_height
        self.ratio = ratio
        self.model_type = model_type
        self.threads = threads

        # Create temporary folder/directories
        self.video2x_cache_folder = video2x_cache_folder
        self.extracted_frames_object = tempfile.TemporaryDirectory(dir=self.video2x_cache_folder)
        self.extracted_frames = self.extracted_frames_object.name
        Avalon.debug_info('Extracted frames are being saved to: {}'.format(self.extracted_frames))

        self.upscaled_frames_object = tempfile.TemporaryDirectory(dir=self.video2x_cache_folder)
        self.upscaled_frames = self.upscaled_frames_object.name
        Avalon.debug_info('Upscaled frames are being saved to: {}'.format(self.upscaled_frames))

        self.preserve_frames = preserve_frames

        # If hardware acceleration enabled, append arguments
        if self.ffmpeg_hwaccel:
            self.ffmpeg_arguments.append('-hwaccel {}'.format(self.ffmpeg_hwaccel))

    def cleanup(self):
        # Delete temp directories when done
        # Avalon framework cannot be used if python is shutting down
        # Therefore, plain print is used
        if not self.preserve_frames:
            print('Cleaning up cache directory: {}'.format(self.extracted_frames))
            self.extracted_frames_object.cleanup()
            print('Cleaning up cache directory: {}'.format(self.upscaled_frames))
            self.upscaled_frames_object.cleanup()

    def _check_model_type(self, args):
        """ Validate upscaling model
        """
        if self.model_type not in MODELS_AVAILABLE:
            raise InvalidModelType('Specified model type not available')

    def _check_arguments(self):
        # Check if arguments are valid / all necessary argument
        # values are specified
        if not self.input_video:
            raise ArgumentError('You need to specify the video to process')
        elif (not self.output_width or not self.output_height) and not self.ratio:
            raise ArgumentError('You must specify output video width and height or upscale factor')
        elif not self.output_video:
            raise ArgumentError('You need to specify the output video name')
        elif not self.method:
            raise ArgumentError('You need to specify the enlarging processing unit')

    def _progress_bar(self, extracted_frames_folders):
        """ This method prints a progress bar

        This method prints a progress bar by keeping track
        of the amount of frames in the input directory/folder
        and the output directory/folder. This is originally
        suggested by @ArmandBernard.
        """
        # Get number of extracted frames
        total_frames = 0
        for folder in extracted_frames_folders:
            total_frames += len([f for f in os.listdir(folder) if f[-4:] == '.png'])

        with tqdm(total=total_frames, ascii=True, desc='Upscaling Progress') as progress_bar:

            # tqdm update method adds the value to the progress
            # bar instead of setting the value. Therefore, a delta
            # needs to be calculated.
            previous_cycle_frames = 0
            while not self.progress_bar_exit_signal:

                try:
                    total_frames_upscaled = len([f for f in os.listdir(self.upscaled_frames) if f[-4:] == '.png'])
                    delta = total_frames_upscaled - previous_cycle_frames
                    previous_cycle_frames = total_frames_upscaled

                    # If upscaling is finished
                    if total_frames_upscaled >= total_frames:
                        return

                    # Adds the detla into the progress bar
                    progress_bar.update(delta)
                except FileNotFoundError:
                    pass

                time.sleep(1)

    def _upscale_frames(self, w2):
        """ Upscale video frames with waifu2x-caffe

        This function upscales all the frames extracted
        by ffmpeg using the waifu2x-caffe binary.

        Arguments:
            w2 {Waifu2x Object} -- initialized waifu2x object
        """

        # Progress bar thread exit signal
        self.progress_bar_exit_signal = False

        # It's easier to do multi-threading with waifu2x_converter
        # The number of threads can be passed directly to waifu2x_converter
        if self.waifu2x_driver == 'waifu2x_converter':

            progress_bar = threading.Thread(target=self._progress_bar, args=([self.extracted_frames],))
            progress_bar.start()

            w2.upscale(self.extracted_frames, self.upscaled_frames, self.ratio, self.threads)
            for image in [f for f in os.listdir(self.upscaled_frames) if os.path.isfile(os.path.join(self.upscaled_frames, f))]:
                renamed = re.sub('_\[.*-.*\]\[x(\d+(\.\d+)?)\]\.png', '.png', image)
                shutil.move('{}\\{}'.format(self.upscaled_frames, image), '{}\\{}'.format(self.upscaled_frames, renamed))
            
            self.progress_bar_exit_signal = True
            progress_bar.join()
            return

        # Create a container for all upscaler threads
        upscaler_threads = []

        # List all images in the extracted frames
        frames = [os.path.join(self.extracted_frames, f) for f in os.listdir(self.extracted_frames) if os.path.isfile(os.path.join(self.extracted_frames, f))]

        # If we have less images than threads,
        # create only the threads necessary
        if len(frames) < self.threads:
            self.threads = len(frames)

        # Create a folder for each thread and append folder
        # name into a list

        thread_pool = []
        thread_folders = []
        for thread_id in range(self.threads):
            thread_folder = '{}\\{}'.format(self.extracted_frames, str(thread_id))
            thread_folders.append(thread_folder)

            # Delete old folders and create new folders
            if os.path.isdir(thread_folder):
                shutil.rmtree(thread_folder)
            os.mkdir(thread_folder)

            # Append folder path into list
            thread_pool.append((thread_folder, thread_id))

        # Evenly distribute images into each folder
        # until there is none left in the folder
        for image in frames:
            # Move image
            shutil.move(image, thread_pool[0][0])
            # Rotate list
            thread_pool = thread_pool[-1:] + thread_pool[:-1]

        # Create threads and start them
        for thread_info in thread_pool:
            # Create thread
            thread = threading.Thread(target=w2.upscale, args=(thread_info[0], self.upscaled_frames, self.output_width, self.output_height))
            thread.name = thread_info[1]

            # Add threads into the pool
            upscaler_threads.append(thread)

        # Start progress bar in a different thread
        progress_bar = threading.Thread(target=self._progress_bar, args=(thread_folders,))
        progress_bar.start()

        # Start all threads
        for thread in upscaler_threads:
            thread.start()

        # Wait for threads to finish
        for thread in upscaler_threads:
            thread.join()
        
        self.progress_bar_exit_signal = True

    def run(self):
        """Main controller for Video2X

        This function controls the flow of video conversion
        and handles all necessary functions.
        """

        # Parse arguments for waifu2x
        # Check argument sanity
        self._check_model_type(self.model_type)
        self._check_arguments()

        # Convert paths to absolute paths
        self.input_video = os.path.abspath(self.input_video)
        self.output_video = os.path.abspath(self.output_video)

        # Add a forward slash to directory if not present
        # otherwise there will be a format error
        if self.ffmpeg_path[-1] != '/' and self.ffmpeg_path[-1] != '\\':
            self.ffmpeg_path = '{}/'.format(self.ffmpeg_path)

        # Check if FFMPEG and waifu2x are present
        if not os.path.isdir(self.ffmpeg_path):
            raise FileNotFoundError(self.ffmpeg_path)
        if not os.path.isfile(self.waifu2x_path) and not os.path.isdir(self.waifu2x_path):
            raise FileNotFoundError(self.waifu2x_path)

        # Initialize objects for ffmpeg and waifu2x-caffe
        fm = Ffmpeg(self.ffmpeg_path, self.ffmpeg_arguments)

        # Initialize waifu2x driver
        if self.waifu2x_driver == 'waifu2x_caffe':
            w2 = Waifu2xCaffe(self.waifu2x_path, self.method, self.model_type)
        elif self.waifu2x_driver == 'waifu2x_converter':
            w2 = Waifu2xConverter(self.waifu2x_path)
        else:
            raise Exception('Unrecognized waifu2x driver: {}'.format(self.waifu2x_driver))

        # Extract frames from video
        fm.extract_frames(self.input_video, self.extracted_frames)

        Avalon.info('Reading video information')
        video_info = fm.get_video_info(self.input_video)
        # Analyze original video with ffprobe and retrieve framerate
        # width, height = info['streams'][0]['width'], info['streams'][0]['height']

        # Find index of video stream
        video_stream_index = None
        for stream in video_info['streams']:
            if stream['codec_type'] == 'video':
                video_stream_index = stream['index']
                break

        # Exit if no video stream found
        if video_stream_index is None:
            Avalon.error('Aborting: No video stream found')
            exit(1)

        # Get average frame rate of video stream
        framerate = float(Fraction(video_info['streams'][video_stream_index]['avg_frame_rate']))
        Avalon.info('Framerate: {}'.format(framerate))

        # Width/height will be coded width/height x upscale factor
        if self.ratio:
            coded_width = video_info['streams'][video_stream_index]['coded_width']
            coded_height = video_info['streams'][video_stream_index]['coded_height']
            self.output_width = self.ratio * coded_width
            self.output_height = self.ratio * coded_height

        # Upscale images one by one using waifu2x
        Avalon.info('Starting to upscale extracted images')
        self._upscale_frames(w2)
        Avalon.info('Upscaling completed')

        # Frames to Video
        Avalon.info('Converting extracted frames into video')

        # Use user defined output size
        fm.convert_video(framerate, '{}x{}'.format(self.output_width, self.output_height), self.upscaled_frames)
        Avalon.info('Conversion completed')

        # Migrate audio tracks and subtitles
        Avalon.info('Migrating audio tracks and subtitles to upscaled video')
        fm.migrate_audio_tracks_subtitles(self.input_video, self.output_video, self.upscaled_frames)
