# MIP_Helper

This is a Python library used in the hbpmip/python-mip Docker image in order to ease developers job.
It provides functions to read and write data from/to the MIP.

For more details, please have a look at
[python-mip](https://github.com/LREN-CHUV/python-base-docker-images/blob/master/python-mip/README.md).


## How to update it

1) Update the library code, update the version number in the __setup.cfg__ file and
optionally the __.md__ version of the README
2) Run the __build.sh__ script in order to generate the __.rst__ version of the README and build the library
3) Commit and push your changes and run the __publish.sh__ script in order to publish the new release on PyPI
