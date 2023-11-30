[![docs](https://img.shields.io/badge/docs-latest-blue.svg)](https://smartmultiprocessing.org)
[![Build Docs](https://github.com/emilyhunt/smartmultiprocessing/actions/workflows/build-docs.yml/badge.svg)](https://smartmultiprocessing.org)

# SmartMultiprocessing
A drop-in replacement for Python's `multiprocessing` library with many extra features, including: memory management, smart task scheduling, a pause button, a GUI, and more.

`SmartMultiprocessing` is ideal for use cases beyond typical `multiprocessing` use, like:

- Running code where memory usage is different depending on input values
- Benchmarking experimental code where memory usage is not well understood
- Running code on a machine where it's important to be able to pause execution/change thread and memory use on the fly
- Being able to monitor the performance of code without having to write your own monitoring library from scratch


## SmartMultiprocessing is in active development!

This project is a spin-out from code that [@emilyhunt](https://github.com/emilyhunt) wrote during her PhD. It's currently in alpha / active development - check back here soon for the first production-ready versions!
