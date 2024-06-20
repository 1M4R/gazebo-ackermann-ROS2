#!/bin/bash

sudo apt update
sudo apt install python3-pip
sudo apt install -y python3-argcomplete
sudo apt install ros-galactic-joint-state-publisher
sudo apt install ros-galactic-vision-msgs
sudo apt install ros-galactic-gazebo-ros-pkgs

pip install --upgrade pip
pip install -r requirements.txt
