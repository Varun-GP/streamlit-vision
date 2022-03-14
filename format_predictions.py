import os
import pytz
from datetime import datetime
import schedule 
import time 
import base64
import rerun

from azure.storage.blob import (
	BlobServiceClient,
	ContainerClient,
	__version__,
)

from azure.core.exceptions import ResourceExistsError,ResourceNotFoundError
import wget
import streamlit as st
#cogniableold storage account
COGNIABLE_OLD_CONNECTION_STRING  = "DefaultEndpointsProtocol=https;AccountName=cogniableold;AccountKey=obxB3FMDXO3xz/pdO96V91Mki7xI1CKop9bhQkCdr5kdTqV8bmGXh15uBafQimQzKr2CjALO4FTUxB8+E2KWgg==;EndpointSuffix=core.windows.net"
CONTAINER_NAME_CGOLD = "awsdata"
blob_service_client_cgold = BlobServiceClient.from_connection_string(COGNIABLE_OLD_CONNECTION_STRING)
cg_bucket = ContainerClient.from_connection_string(
	conn_str=COGNIABLE_OLD_CONNECTION_STRING, container_name=CONTAINER_NAME_CGOLD)

import plotly.graph_objects as go
import kaleido
import pandas as pd
from streamlit.report_thread import get_report_ctx
import mapping

key_global = ""

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

def visualize_prob(pred_dict):
	for i in range(len(pred_dict)):

		fig = go.Figure(go.Indicator(
			mode = "gauge+number",
			value = pred_dict[i],
			domain = {'x': [0, 1], 'y': [0, 1]},
			title = {'text': "CONFIDENCE", 'font': {'size': 18}},
			gauge = {
				'axis': {'range': [0, 100], 'tickwidth': 3, 'tickcolor': "white"},
				'bar': {'color': "seagreen", 'thickness':0.50},
				'bgcolor': "black",
				'borderwidth': 3,
				'bordercolor': "white",
				#'steps': [
				#   {'range': [0, 25], 'color': 'darkred'},
				#    {'range': [25, 50], 'color': 'lightyellow'},
				#    {'range': [50, 75], 'color': 'darkorange'},
				#    {'range': [75, 100], 'color': 'darkgreen'}],
				#'threshold': {
				#    'line': {'color': "red", 'width': 1},
				#    'thickness': 0.75,
				#    'value': 85}
				}
				))

		fig.update_layout(paper_bgcolor = "black", font = {'color': "white", 'family': "Arial"},autosize=False,
			width=500,
			height=500)

		#fig.show()

		fig.write_image("plot_"+str(i)+".png",  format="png", engine="kaleido")


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

def check_prediction_update(key_global):
	ctx = get_report_ctx()
	key_global = str(ctx.session_id)[-5:]
	target_bucket = 'visionmodel'

	# pred_object = cg_bucket.list_blobs(name_starts_with="Model_July_24Classes")
	pred_object = get_bucket_contents(str(target_bucket))
	line = open('time.txt','r').readline()
	date, time  = line.rsplit(' ')[0].strip(), line.rsplit(' ')[1].strip()
	yyyy,m,d = date.rsplit('-')[0].strip(), date.rsplit('-')[1].strip(), date.rsplit('-')[2].strip()
	hh,mm,s = time.rsplit(':')[0].strip(), time.rsplit(':')[1].strip(), str(time.rsplit(':')[2]).split('+')[0].strip()
	timestamp = pytz.utc.localize(datetime(int(yyyy), int(m), int(d), int(hh), int(mm), int(float(s))))
	is_modified = False
	url = ""
	for blob in pred_object:
		if blob.key.endswith(".log") and "Predictions" in str(blob.key) and str(key_global) in str(blob.key) and blob.last_modified > timestamp:
			#print(blob.last_modified)
			# url = "https://cogniableold.blob.core.windows.net/awsdata/" + str(blob.key)
			url = "https://visionmodel.s3.che01.cloud-object-storage.appdomain.cloud/" + str(blob.key)
			with open('time.txt','w+') as l:
				l.write(str(blob.last_modified))
			l.close()
			is_modified = True
	
	return is_modified, url

def get_table_download_link(table):
	csv = table.to_csv(index=False)
	
	b64 =  base64.b64encode(csv.encode()).decode()
	href = f'<a href="data:file/csv;base64,{b64}" download="assessment_predictions.csv">Download Predictions</a>'
	return href

def get_taget_table_download_link(table):
	csv = table.to_csv(index=False)
	
	b64 =  base64.b64encode(csv.encode()).decode()
	href = f'<a href="data:file/csv;base64,{b64}" download="assessment_targets.csv">Download Targets</a>'
	return href

def display_pred():
	prediction_list = []
	confidence_threshold = 70.0
	lines = open('prediction.txt','r').readlines()

	if "squinting eyes" in lines[0]:
		attention = str(lines[0].rstrip())
		st.write(attention)
		return attention
			
	if "eye contact" in lines[0]:
		attention = str(lines[0].rstrip())
		st.write(attention)
		return attention

	if "Follow gaze" in lines[0]:
		attention = str(lines[0].rstrip())
		st.write(attention)
		return attention

	if "Finger Pointing" in lines[0]:
		pointing = str(lines[0].rstrip())
		st.write(pointing)
		return pointing
	
	
	if "Face Expression" in lines[0]:
		import plotly.graph_objects as go

		def plot_emotions_temporal_data():
			emotions = open('prediction.txt','r').readlines()
			#print(emotions)
			total_duration = float(str(emotions[0]).rstrip().split('duration ')[1])

			happy_x, sad_x, disgust_x, surprise_x, angry_x, fear_x, neutral_x = ([] for i in range(7))
			happy, sad, disgust, surprise, angry, fear, neutral = ([] for i in range(7))

			try: 
				for emotion in emotions:
					if 'happy' in emotion:
						happy.append(str(emotion).rstrip().split('seconds')[0].split('at ')[1])
						for item in happy:
							happy_x = item.rstrip().split(' ')
						happy_x = [float(x) for x in happy_x]
					if 'sad' in emotion:
						sad.append(str(emotion).rstrip().split('seconds')[0].split('at ')[1])
						for item in sad:
							sad_x = item.rstrip().split(' ')
						sad_x = [float(x) for x in sad_x]    
					if 'angry' in emotion:
						angry.append(str(emotion).rstrip().split('seconds')[0].split('at ')[1])
						for item in angry:
							angry_x = item.rstrip().split(' ')
						angry_x = [float(x) for x in angry_x]
					if 'disgust' in emotion:
						disgust.append(str(emotion).rstrip().split('seconds')[0].split('at ')[1])
						for item in disgust:
							disgust_x = item.rstrip().split(' ')
						disgust_x = [float(x) for x in disgust_x]
					if 'fear' in emotion:
						fear.append(str(emotion).rstrip().split('seconds')[0].split('at ')[1])
						for item in fear:
							fear_x = item.rstrip().split(' ')
						fear_x = [float(x) for x in fear_x]
					if 'surprise' in emotion:
						surprise.append(str(emotion).rstrip().split('seconds')[0].split('at ')[1])
						for item in surprise:
							surprise_x = item.rstrip().split(' ')
						surprise_x = [float(x) for x in surprise_x]
					if 'neutral' in emotion:
						neutral.append(str(emotion).rstrip().split('seconds')[0].split('at ')[1])
						for item in neutral:
							neutral_x = item.rstrip().split(' ')
						neutral_x = [float(x) for x in neutral_x]

				happy_y = [1] * len(happy_x)
				angry_y = [2] * len(happy_x)
				sad_y = [3] * len(happy_x)
				disgust_y = [4] * len(happy_x)
				surprise_y = [5] * len(happy_x)
				neutral_y = [6] * len(happy_x)
				fear_y = [7] * len(happy_x)

				fig = go.Figure()

				fig.update_layout(
					title="Temporal Events of Facial Expression (video duration: "+str(total_duration)+" seconds)",
					xaxis_title="Time (seconds)",title_x = 0.5,
					font=dict(
						family="Courier New, monospace",
						size=15,
						color="#008900"
					),
					yaxis_visible=False, yaxis_showticklabels=False,
					legend=dict(traceorder="reversed",
					title_font_family="Times New Roman",
					font=dict(
						family="Courier",
						size=15,
						color="Green"
					),
					bgcolor="White",
					bordercolor="Green",
					borderwidth=2
				)
					

				)

				# Add traces
				fig.add_trace(go.Scatter(x=happy_x, y=happy_y,
									mode='markers',
									name='Happy'))
				fig.add_trace(go.Scatter(x=sad_x, y=sad_y,
									mode='markers',
									name='Sad'))
				fig.add_trace(go.Scatter(x=angry_x, y=angry_y,
									mode='markers',
									name='Angry'))
				fig.add_trace(go.Scatter(x=disgust_x, y=disgust_y,
									mode='markers',
									name='Disgust'))
				fig.add_trace(go.Scatter(x=surprise_x, y=surprise_y,
									mode='markers',
									name='Surprise'))
				fig.add_trace(go.Scatter(x=fear_x, y=fear_y,
									mode='markers',
									name='Fear'))                    
				fig.add_trace(go.Scatter(x=neutral_x, y=neutral_y,
									mode='markers',
									name='Neutral'))

				return fig
			except:
				pass

		
		fig = plot_emotions_temporal_data()
		st.plotly_chart(fig)
		return fig

	if "Video Understanding" in lines[0]:

		import ast
		import plotly.graph_objects as go

		dance_x, run_x, sit_x, stand_x, walk_x, answerphone_x, holdsth_x, hit_x, listensb_x, talk_x, watchsb_x = ([] for i in range(11))
		dance_x_, run_x_, sit_x_, stand_x_, walk_x_, answerphone_x_, holdsth_x_, hit_x_, listensb_x_, talk_x_, watchsb_x_ = ([] for i in range(11))

		read_file = open('prediction.txt','r').readlines()


		dance_x, run_x, sit_x, stand_x, walk_x, answerphone_x, holdsth_x, hit_x, listensb_x, talk_x, watchsb_x = ast.literal_eval(read_file[1]), ast.literal_eval(read_file[2]),ast.literal_eval(read_file[3]),ast.literal_eval(read_file[4]),ast.literal_eval(read_file[5]),ast.literal_eval(read_file[6]),ast.literal_eval(read_file[7]),ast.literal_eval(read_file[8]),ast.literal_eval(read_file[9]),ast.literal_eval(read_file[10]),ast.literal_eval(read_file[11])
		dance_x_, run_x_, sit_x_, stand_x_, walk_x_, answerphone_x_, holdsth_x_, hit_x_, listensb_x_, talk_x_, watchsb_x_ = ast.literal_eval(read_file[12]), ast.literal_eval(read_file[13]),ast.literal_eval(read_file[14]),ast.literal_eval(read_file[15]),ast.literal_eval(read_file[16]),ast.literal_eval(read_file[17]),ast.literal_eval(read_file[18]),ast.literal_eval(read_file[19]),ast.literal_eval(read_file[20]),ast.literal_eval(read_file[21]),ast.literal_eval(read_file[22])


		def plot_events_of_interest(dance_x, run_x, sit_x, stand_x, walk_x, answerphone_x, holdsth_x, hit_x, listensb_x, talk_x, watchsb_x, who):


			dance_y = [1] * len(dance_x)
			run_y = [2] * len(run_x)
			sit_y = [3] * len(sit_x)
			stand_y = [4] * len(stand_x)
			walk_y = [5] * len(walk_x)
			answerphone_y = [6] * len(answerphone_x)
			holdsth_y = [7] * len(holdsth_x)
			hit_y = [8] * len(hit_x)
			listensb_y = [9] * len(listensb_x)
			talk_y = [10] * len(talk_x)
			watchsb_y = [11] * len(watchsb_x)

			fig = go.Figure()

			fig.update_layout(
								title="Temporal Events of Interest - "+str(who),
								xaxis_title="Time (seconds)",title_x = 0.5,
								font=dict(
									family="Courier New, monospace",
									size=15,
									color="#008900"
								),
								yaxis_visible=False, yaxis_showticklabels=False,
								legend=dict(traceorder="reversed",
								title_font_family="Times New Roman",
								font=dict(
									family="Courier",
									size=15,
									color="Green"
								),
								bgcolor="White",
								bordercolor="Green",
								borderwidth=2
							)
								

							)

			# Add traces
			fig.add_trace(go.Scatter(y=dance_y, x=dance_x,
												mode='markers',
												name='Dancing'))
			fig.add_trace(go.Scatter(y=run_y, x=run_x,
												mode='markers',
												name='Running'))
			fig.add_trace(go.Scatter(y=sit_y, x=sit_x,
												mode='markers',
												name='Sitting'))
			fig.add_trace(go.Scatter(y=stand_y, x=stand_x,
												mode='markers',
												name='Standing'))
			fig.add_trace(go.Scatter(y=walk_y, x=walk_x,
												mode='markers',
												name='Walking'))
			fig.add_trace(go.Scatter(y=answerphone_y, x=answerphone_x,
												mode='markers',
												name='Answering Phone'))                    
			#fig.add_trace(go.Scatter(y=holdsth_y, x=holdsth_x,	mode='markers',	name='Holding / Carrying Something'))
			fig.add_trace(go.Scatter(y=holdsth_y, x=holdsth_x,
												mode='markers',
												name='Holding Object / Oblique Toys'))
			fig.add_trace(go.Scatter(y=hit_y, x=hit_x,
												mode='markers',
												name='Hitting / Fighting'))
			#fig.add_trace(go.Scatter(y=listensb_y, x=listensb_x,mode='markers',	name='Listening to Someone'))
			fig.add_trace(go.Scatter(y=listensb_y, x=listensb_x,
												mode='markers',
												name='Instruction Engagement'))
			#fig.add_trace(go.Scatter(y=talk_y, x=talk_x,mode='markers',name='Talking to Someone'))
			fig.add_trace(go.Scatter(y=talk_y, x=talk_x,
												mode='markers',
												name='Engagement'))
			fig.add_trace(go.Scatter(y=watchsb_y, x=watchsb_x,
												mode='markers',
												name='Watching Someone'))
			#fig.show()
			return fig
		
		fig1 = plot_events_of_interest(dance_x, run_x, sit_x, stand_x, walk_x, answerphone_x, holdsth_x, hit_x, listensb_x, talk_x, watchsb_x, "Child")
		fig2 = plot_events_of_interest(dance_x_, run_x_, sit_x_, stand_x_, walk_x_, answerphone_x_, holdsth_x_, hit_x_, listensb_x_, talk_x_, watchsb_x_, "Play Partner")
		st.plotly_chart(fig1)
		st.plotly_chart(fig2)	
		return fig1	
		
	time_stamps = [(str(str(line).rsplit('-')[2])+" : "+str(str(line).rsplit('-')[3])) for line in lines if "with probability" in line and "****----****" in line and float(line.rstrip().split('||')[-1].strip('.')) > confidence_threshold]
	lines = [(str(line).rsplit('****----****')[1].rstrip(),str(line).rsplit('||')[-1].strip('.')) for line in lines if "with probability" in line and "****----****" in line]
	lines = [(float(x[1].rstrip().strip('.')),str(x[0]).replace('.',' ').replace('Yes','').replace('None','').replace('No.','')) for x in lines if ("." in str(x[0]) or " "in str(x[0])) and float(x[1].rstrip().strip('.')) > confidence_threshold]

	probs =[y[0] for y in lines]

	preds = [y[1] for y in lines]
		
	class_pred = '<p style="font-family:sans-serif; color:Green; font-size: 17px;">Class Predictions</p>'
	st.markdown(class_pred, unsafe_allow_html=True)
	#classes = lines
	#classes = dict(tuple(classes))
	visualize_prob(probs)
	#table = pd.DataFrame({"Classes": classes.values(), "Confidence": classes.keys(),"Time Interval ":time_stamps})
	table = pd.DataFrame({"Classes": preds, "Confidence": probs,"Time Interval ":time_stamps})

	table.index = [""] * len(table)
	st.table(table)
	#new = pd.DataFrame.from_dict(table)
	#concat_df = pd.DataFrame.from_dict([{'Classes':"Video","Confidence":str(url)}])
	#table = pd.concat([concat_df,new.loc[:]]).reset_index(drop=True)

	st.markdown(get_table_download_link(table),unsafe_allow_html=True)

	for i in enumerate(preds):
		new_title = '<p style="font-family:sans-serif; color:Green; font-size: 17px;">'+"Class Name: "+str(i[1])+'</p>'
		st.markdown(new_title, unsafe_allow_html=True)
		st.image("plot_"+str(i[0])+".png", width = 300)

	class_pred = '<p style="font-family:sans-serif; color:Green; font-size: 17px;">Target Details</p>'
	st.markdown(class_pred, unsafe_allow_html=True)
	# display mapping
	class_mapping = [mapping.target_mapping.get(str(c)) for c in preds]
	table_mapping = pd.DataFrame({"Classes": preds, "Targets": class_mapping})
	table_mapping.index = [""] * len(table_mapping)
	st.table(table_mapping)
	st.markdown(get_taget_table_download_link(table_mapping),unsafe_allow_html=True)

	if os.path.exists("prediction.txt"):
		os.remove("prediction.txt")
		#st.write('removed old file')
	else:
		pass
		
	

def timer():
	print("Checking for updates...")
	status, url = check_prediction_update(key_global)
	print(status, url)

	if status == True:
		wget.download(str(url),'prediction.txt')
		lines = open('prediction.txt','r').readline()
		ret_ = display_pred()

		st.info("Note: Refresh your browser tab if you want to try on a new video.")
		st.stop()
		
		if ret_ == "Restart":
			rerun.rerun()


def get_pred_main(key):

	schedule.every(10).seconds.do(timer)
	global key_global
	key_global = key
	while True:
		schedule.run_pending()
		time.sleep(1)
