## Running VEDA locally using docker

This directory is the current state of the work to docker-ize VEDA so it can be run locally. 

## Setup to run

The [edx-video-pipeline](http://github.com/edx/edx-video-pipeline), [edx-video-worker](github.com/edx/edx-video-worker), and [v_videocompile](http://github.com/yro/v_videocompile) should all be downloaded in one directory and an environment variable ```VEDA_WORKSPACE``` set to point to the directory:  

```
export VEDA_WORKSPACE=/Users/sofiyasemenova/veda
```

### Images

The images can be found on docker hub:
- [Http](https://hub.docker.com/r/ssemenova/veda-http/)
- [Pipeline](https://hub.docker.com/r/ssemenova/veda-pipeline/)
- [Deliver](https://hub.docker.com/r/ssemenova/veda-deliver/)
- [Encode](https://hub.docker.com/r/ssemenova/veda-encode/)
- [Rabbit MQ](https://hub.docker.com/r/ssemenova/veda-rabbitmq/)

## Work to be done

This is probably not an exhaustive list:

- The http endpoint works, but work needs to be done to connect all the containers together and have them speak over local ports instead of calling ec2 containers.
- The database settings file contains the right database configuration, but we need to actually make sure the database works and is set up locally.
- I have done very little with the Rabbit MQ container. The image is based off the base veda docker image, but has nothing rabbit-specific. I'm not sure about what work needs to be done here.
