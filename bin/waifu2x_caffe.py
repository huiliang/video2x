#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Name: Waifu2x Caffe Driver
Author: K4YT3X
Date Created: Feb 24, 2018
Last Modified: March 4, 2019

Description: This class controls waifu2x
engine
"""
from avalon_framework import Avalon
import subprocess
import threading


class Waifu2xCaffe:
    """This class communicates with waifu2x cui engine

    An object will be created for this class, containing information
    about the binary address and the processing method. When being called
    by the main program, other detailed information will be passed to
    the upscale function.
    """

    def __init__(self, waifu2x_path, method, model_type):
        self.waifu2x_path = waifu2x_path
        self.method = method
        self.model_type = model_type
        self.print_lock = threading.Lock()

    def upscale(self, folderin, folderout, width, height):
        """This is the core function for WAIFU2X class

        Arguments:
            folderin {string} -- source folder path
            folderout {string} -- output folder path
            width {int} -- output video width
            height {int} -- output video height
        """

        # Print thread start message
        self.print_lock.acquire()
        Avalon.debug_info('[upscaler] Thread {} started'.format(threading.current_thread().name))
        self.print_lock.release()

        # Create string for execution
        # execute = ['{}'.format(self.waifu2x_path), '-p', self.method, '-I', 'png', '-i', '\"{}\"'.format(folderin), '-e', 'png', '-o', folderout, '-w', str(width), '-h', str(height), '-n', '3', '-m', 'noise_scale', '-y', self.model_type]
        execute = '\"{}\" -p {} -I png -i \"{}\" -e png -o {} -w {} -h {} -n 3 -m noise_scale -y {}'.format(
            self.waifu2x_path, self.method, folderin, folderout, width, height, self.model_type)
        print('Executing: {}'.format(execute))
        subprocess.run(execute, shell=True, check=True)

        # Print thread exiting message
        self.print_lock.acquire()
        Avalon.debug_info('[upscaler] Thread {} exiting'.format(threading.current_thread().name))
        self.print_lock.release()
