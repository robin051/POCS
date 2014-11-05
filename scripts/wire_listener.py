#!/usr/bin/env python

import zmq

context = zmq.Context()
socket = context.socket(zmq.SUB)

socket.setsockopt_string(zmq.SUBSCRIBE, '')
socket.connect('tcp://localhost:6500')

while True:
	print(socket.recv())