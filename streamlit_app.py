# Usage: streamlit run app.py
import streamlit as st
import pandas as pd
import numpy as np
import os 
import sys
import wget
#from pytube import YouTube
from PIL import Image
import subprocess as sp
from azure.storage.blob import (
	BlobServiceClient,
	ContainerClient,
	__version__,
)
import pytz
from datetime import datetime
from azure.core.exceptions import ResourceExistsError,ResourceNotFoundError
import format_predictions
import tempfile
import shutil
import time
import string
import random
#cogniableold storage account
COGNIABLE_OLD_CONNECTION_STRING  = "DefaultEndpointsProtocol=https;AccountName=cogniableold;AccountKey=obxB3FMDXO3xz/pdO96V91Mki7xI1CKop9bhQkCdr5kdTqV8bmGXh15uBafQimQzKr2CjALO4FTUxB8+E2KWgg==;EndpointSuffix=core.windows.net"
CONTAINER_NAME_CGOLD = "awsdata"
blob_service_client_cgold = BlobServiceClient.from_connection_string(COGNIABLE_OLD_CONNECTION_STRING)
cg_bucket = ContainerClient.from_connection_string(
	conn_str=COGNIABLE_OLD_CONNECTION_STRING, container_name=CONTAINER_NAME_CGOLD)

from streamlit.report_thread import get_report_ctx
#import youtube_dl

import ibm_boto3
from ibm_botocore.client import Config, ClientError

# Constants for IBM COS values
COS_ENDPOINT = "https://s3.che01.cloud-object-storage.appdomain.cloud" # Current list avaiable at https://control.cloud-object-storage.cloud.ibm.com/v2/endpoints
COS_API_KEY_ID = "87hyUyV47X0bvi_cXGqA-3cg3wYRz7G9XZzj26Dp3CSR" # eg "W00YixxxxxxxxxxMB-odB-2ySfTrFBIQQWanc--P3byk"
COS_INSTANCE_CRN = "crn:v1:bluemix:public:cloud-object-storage:global:a/ed5af9d7ed5a423cbd1d6f677410bc4d:2aff4f76-99d5-4b56-8c87-75d9f5b13082::" # eg "crn:v1:bluemix:public:cloud-object-storage:global:a/3bf0d9003xxxxxxxxxx1c3e97696b71c:d6f04d83-6c4f-4a62-a165-696756d63903::"

# Create resource
cos = ibm_boto3.resource("s3",
    ibm_api_key_id=COS_API_KEY_ID,
    ibm_service_instance_id=COS_INSTANCE_CRN,
    config=Config(signature_version="oauth"),
    endpoint_url=COS_ENDPOINT
)


bucket_name = 'visionmodel'

def download_video(user_input):
	# test user_input = "https://www.youtube.com/watch?v=yMgx2lVjf5I"
	# only at deployment
	#path_main = "/app/AlphAction"	
	#path_main = str(os.path.abspath(os.getcwd())).rpartition('/')[0]
	#tempfile.tempdir = str(path_main)+"/input/"

	if "tube" in user_input:
		#yt = YouTube(user_input)
		#out_file = yt.streams.first().download()
		#os.rename(out_file,'test.mp4')
		#ydl_opts = {'outtmpl': 'test.mp4'}
		#with youtube_dl.YoutubeDL(ydl_opts) as ydl:
		#	ydl.download([str(user_input)])
			#st.write("inside")
			#time.sleep(30)
		vid = 'test.mp4'
		os.system("youtube-dl  -f 'bestvideo[ext=mp4]+bestaudio[ext=m4a]' "+str(user_input)+" --output 'test.mp4'")

		#if os.path.exists("test.mp4"):
		#	st.write("Video downloaded")

	else:
		st.info("Not a valid YouTube URL. ")
		wget.download(user_input,'test.mp4')
	
	
	#return path_main


def get_bucket_contents(bucket_name):
    target_files = []
    print("Retrieving bucket contents from: {0}".format(bucket_name))
    try:
        files = cos.Bucket(bucket_name).objects.all()
        for file in files:
            print("Item: {0} ({1} bytes).".format(file.key, file.size))
            target_files.append(file)
    except ClientError as be:
        print("CLIENT ERROR: {0}\n".format(be))
    except Exception as e:
        print("Unable to retrieve bucket contents: {0}".format(e))

    return target_files

def check_AllclusterNode_state():
	#state_object = cg_bucket.list_blobs(name_starts_with="Model_July_24Classes")
	target_bucket = 'visionmodel'

	state_object = get_bucket_contents(str(target_bucket))
	is_modified = False
	url = ""
	states = []
	for blob in state_object:
		if blob.key.endswith(".txt") and "States" in str(blob.key):
			#print(blob.last_modified)
			#print(blob.key)
			url = "https://visionmodel.s3.che01.cloud-object-storage.appdomain.cloud/" + str(blob.key)
			states.append(url)
	
	return states

def multi_part_upload(bucket_name, item_name, file_path):
    try:
        print("Starting file transfer for {0} to bucket: {1}\n".format(item_name, bucket_name))
        # set 5 MB chunks
        part_size = 1024 * 1024 * 5

        # set threadhold to 15 MB
        file_threshold = 1024 * 1024 * 15

        # set the transfer threshold and chunk size
        transfer_config = ibm_boto3.s3.transfer.TransferConfig(
            multipart_threshold=file_threshold,
            multipart_chunksize=part_size
        )

        # the upload_fileobj method will automatically execute a multi-part upload
        # in 5 MB chunks for all files over 15 MB
        with open(file_path, "rb") as file_data:
            cos.Object(bucket_name, item_name).upload_fileobj(
                Fileobj=file_data,
                Config=transfer_config
            )

        print("Transfer for {0} Complete!\n".format(item_name))
    except ClientError as be:
        print("CLIENT ERROR: {0}\n".format(be))
    except Exception as e:
        print("Unable to complete multi-part upload: {0}".format(e))

def dump_video(model_type):

	ctx = get_report_ctx()
	user_key = str(ctx.session_id)[-5:]
	st.write("User key", user_key)
	bucket_name = 'visionmodel'

	# Put video on instance one as queue
	remote_file_name_path = ("Model_July_24Classes/ONLINE_TEST_VIDEOS/test_"+str(1)+str(user_key)+str(model_type)+".mp4")
	backup_path = "Model_July_24Classes/Backup/test_"+str(user_key)+str(model_type)+".mp4"
	print("remote_file_name_path",remote_file_name_path)

	#blob_client = cg_bucket.get_blob_client(remote_file_name_path)
	#blob_client_backup = cg_bucket.get_blob_client(backup_path)

	#with open('test.mp4', 'rb') as data:
		#blob_client.upload_blob(data, overwrite=True)
	multi_part_upload(bucket_name,remote_file_name_path, 'test.mp4' )

	#with open('test.mp4', 'rb') as data:
		#blob_client_backup.upload_blob(data, overwrite=True)
	multi_part_upload(bucket_name,backup_path, 'test.mp4' )
		
	return user_key
		
def get_predictions(user_input, model_type):
	
	st.spinner("Downloading Video...")
	with open('time.txt','w+') as f:
		f.write(str(datetime.now()))
	f.close()
	download_video(str(user_input))
	st.success("Video download successful")

	key = dump_video(model_type)
	st.success("Predictions in process...")
	format_predictions.get_pred_main(key)
	
	def run_command(args):
		"""Run command, transfer stdout/stderr back into Streamlit and manage error"""
		st.info(f"Running '{' '.join(args)}'")
		result = sp.run(args, capture_output=True, text=True)
		try:
			result.check_returncode()
			st.info(result.stdout)
		except sp.CalledProcessError as e:
			st.error(result.stderr)
			raise e

	dir_path = os.listdir(".")
	for vids in dir_path:
		if vids.endswith(".mp4"):
			os.remove(os.path.join(".",vids))
	else:
		pass
	
	if os.path.exists("prediction.txt"):
		os.remove("prediction.txt")
		#st.write('removed old file')
	else:
		pass

def get_predictions_(user_input, model_type):
	
	with open('time.txt','w+') as f:
		f.write(str(datetime.now()))
	f.close()
	#download_video(str(user_input))
	st.success("Video upload successful")
	key = dump_video(model_type)
	st.success("Predictions in process...")

	format_predictions.get_pred_main(key)
	
	def run_command(args):
		"""Run command, transfer stdout/stderr back into Streamlit and manage error"""
		st.info(f"Running '{' '.join(args)}'")
		result = sp.run(args, capture_output=True, text=True)
		try:
			result.check_returncode()
			st.info(result.stdout)
		except sp.CalledProcessError as e:
			st.error(result.stderr)
			raise e

	dir_path = os.listdir(".")
	for vids in dir_path:
		if vids.endswith(".mp4"):
			os.remove(os.path.join(".",vids))
	else:
		pass
	
	if os.path.exists("prediction.txt"):
		os.remove("prediction.txt")
		#st.write('removed old file')
	else:
		pass

def run(user_input, model_type):
	#check.run()
	get_predictions(user_input, model_type)

def run_(user_input, model_type):
	get_predictions_(user_input, model_type)

def about():
	string = "\n\n Our method identifies the classes responsible for determining Autistic or Neurotypical behaviours from a video."

	return string

def application():

	dir_path = os.listdir(".")
	for vids in dir_path:
		if vids.endswith(".mp4"):
			os.remove(os.path.join(".",vids))
	else:
		pass
	
	if os.path.exists("prediction.txt"):
		os.remove("prediction.txt")
		#st.write('removed old file')
	else:
		pass

	image_logo = Image.open('logo.jpg')
	st.sidebar.image(image_logo, use_column_width=True)
	st.sidebar.title("ASD Assessment System")
	
	app_mode = st.sidebar.selectbox("Select Mode",
		["About","Run Prediction"])
	if app_mode == "About":
		
		st.title("**ASD Class Predictor**")
		st.write("\n\n")
		st.markdown(about())
		image = Image.open('model.png')
		st.image(image, caption='Vision Model ASD/Neurotypical Class Predictor')

	elif app_mode == "Run Prediction":
		run_the_app()


def run_the_app():
	user_input = st.text_input("Video URL   ", "")
	upload = st.empty()

	with upload:
		video_input = st.file_uploader("Upload Video",type=['mp4'])

	model_options = ("Behavior","Motor","Video Understanding - Common","Stereotypies Squinting (Spontaneous)","Eye Contact","Joint Attention - Follow Gaze","Facial Expressions","Imitation","Joint Attention - Pointing to Someone/Something")

	options = list(range(len(model_options)))

	selected_model = st.selectbox("Assessment Type", options, format_func = lambda x: model_options[x])

	# Show instructions
	if str(selected_model) == "5":
		image_gaze = Image.open('child.png')
		st.image(image_gaze, caption='Illustration for Joint Attention follow gaze')

	
	submit = st.button('Get Prediction')
	if submit:
		st.info("Note: Please wait for 10 minutes and keep your browser tab open.")
	files = os.listdir()
	for item in files:
		try:
			if "test" in item:
				os.remove(item)
		except:
			pass

	if video_input is not None and submit == True and "http" not in user_input:
		tfile  = tempfile.NamedTemporaryFile(delete = True, suffix='.mp4')
		tfile.write(video_input.read())

		shutil.copy(tfile.name, 'test.mp4')

		#st.write(str(tfile.name))
		run_(video_input, selected_model)	
		
	if submit and "http" in user_input and video_input is None:
		run(user_input, selected_model)
		
	if submit == True and "http" not in user_input and video_input is None:
		st.write("Invalid URL")
	if "http" in user_input and video_input:
		st.write("Please provide either an URL or Upload a Video")
		st.stop()


if __name__ == '__main__':
	application()
	print("Application running normal..")
