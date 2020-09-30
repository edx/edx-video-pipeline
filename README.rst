This repository has been archived and is no longer supported—use it at your own risk. This repository may depend on out-of-date libraries with security issues, and security updates will not be provided. Pull requests against this repository will also not be merged.

=================================
edx-video-pipeline (A.K.A "Veda")
=================================

Video encode automation django app/control node for edx-platform
----------------------------------------------------------------

**The video pipeline performs the following tasks**
- Ingest (Discovery, Cataloging, Sending tasks to worker cluster)
- Delivery
- Storage
- Maintenance

The video pipeline seeks modularity between parts, and for each part to operate as cleanly and independently as possible.
Each course's workflow operates independently, and workflows can be configured to serve a variety of endpoints.

INGEST:
Currently we ingest remote video from edx-platform via the Studio video upload tool. The videos are discovered by the video pipeline and ingested upon succcessful upload, renamed to an internal ID schema, and routed to the appropriate transcode task cluster.

TRANSCODE:
code for this is housed at https://github.com/edx/edx-video-worker

DELIVERY:
Uploads product videos to specific third-party destinations (YT, AWS, 3Play, cielo24), retrieves URLs/Statuses/products.

STORAGE:
A specified AWS S3 bucket=

MAINTENANCE:
Logging, Data dumping, Celery node status and queue information



.. image:: https://travis-ci.org/edx/edx-video-pipeline.svg?branch=master
    :target: https://travis-ci.org/edx/edx-video-pipeline
