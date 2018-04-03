# dropbox-sync
This script copies files from a local directory to your remote Dropbox account.

If a filename exists at the destination, it is overwritten if the local file has a more recent modified timestamp and the file has updated content as determined using [Dropbox’s content hash algorithm](https://www.dropbox.com/developers/reference/content-hash).

Remote files that have been deleted locally are not touched.

This script is adapted from the example code in the [Dropbox API](https://github.com/dropbox/dropbox-sdk-python).

## Setup

Clone this repo.

Install the dropbox python API using pip:
```
$ pip install dropbox
```

#### Obtaining an Access Token
You need to create an Dropbox Application to make API requests. Go to [https://dropbox.com/developers/apps](https://dropbox.com/developers/apps). Once you've created an app, you can go to the app’s console and generate an access token for your own Dropbox account.

## Run
```
$ python sync.py /source/path /remote/dropbox/path -t your_access_token
```
