import os #file handling
import queue #queues
import time #waiting
import datetime #datetime math
import threading #multiprocess
import subprocess #ffmpeg calls
import math #ceil for Twitch segments

from moviepy import VideoFileClip, concatenate_videoclips
from moviepy.audio.fx.AudioFadeIn import AudioFadeIn
#from moviepy.video.fx.MultiplySpeed import MultiplySpeed
#from moviepy.audio.fx.MultiplyVolume import MultiplyVolume
from moviepy.audio.fx.AudioFadeOut import AudioFadeOut

from TOOLS.Twitch import getLatestTwitchVODs
from TOOLS.Twitch import durationStr2Sec
from TOOLS.Twitch import downloadTwitchClip

from TOOLS.AudioFingerprint import extract_audio_from_mp4
from TOOLS.AudioFingerprint import find_sound_timestamp

from TOOLS.FMS import getMatchesFromFMS
from TOOLS.FMS import rewrapMatches

from TOOLS.logging import listNotInLog
from TOOLS.logging import match2str

from TOOLS.thumbnails import generateThumbnail
from TOOLS.YouTube import formatYouTubeTitle
from TOOLS.YouTube import upload_video
from TOOLS.TBA import translateMatchString
from TOOLS.TBA import postTheBlueAlliance

# determine local timezone
device_timezone = datetime.datetime.now().astimezone().tzinfo
#event_timezone = datetime.timezone(datetime.timedelta(seconds=2*60*60), 'Israel Standard Time')

# download buffer "constants" (prevents missing the start or end due to Twitch stream delay)
twitch_download_pre_buffer = 2
twitch_download_post_buffer = 8

# Define the queues
queue_build = queue.Queue()
queue_send = queue.Queue()

VODs = {}

def incrementCountText(textObject):
    textLabel = textObject.text()[0:7]
    value = int(textObject.text()[7:])
    textObject.setText(textLabel+str(value+1))

def watch(twitch_user_id:str, stop_event, CREDENTIALS, latestVODs:dict=VODs):
    """
    Checks for new VODs on a Twitch channel

    Args:
        twitch_user_id (str): User ID of a Twitch channel
        stop_event: (bool) or threading.Event(), used to stop processing
        latestVODs (dict): details of VODs found

    """
    if stop_event.is_set():
        return
    
    # get the latest VODs for a user ID (pagination ignored)
    new_VODs_list = getLatestTwitchVODs(CREDENTIALS['Twitch_clientID'], CREDENTIALS['Twitch_clientSecret'], twitch_user_id)

    # covert information into more useable form
    new_VODs = {}
    for vod in new_VODs_list:
        created_at_datetime = datetime.datetime.fromisoformat(vod['created_at'])
        vod['created_at'] =  created_at_datetime.astimezone(device_timezone).replace(tzinfo=None)
        vod['duration'] = durationStr2Sec(vod['duration'])
        new_VODs[vod['id']] = vod
    
    newIDs = [vodID for vodID in new_VODs.keys() if not(vodID in VODs.keys())]
    if newIDs:
        print('New VODs!', newIDs)
    
    # Clear the existing VODs and append all new VODs to the shared list
    latestVODs.update(new_VODs)
    
    # Schedule the function to run again after 15 minutes
    threading.Timer(15*60, watch, args=(twitch_user_id, stop_event, CREDENTIALS, latestVODs)).start()

def process_queue_seek(user_data, stop_event, QLabelCounter, CREDENTIALS):
    """
    Looks for new matches from FMS and adds them to the queue

    Args:
        user_data (dict): user inputs from FRUIT GUI
        stop_event: (bool) or threading.Event(), used to stop processing
        QLabelCounter: PYQT QLabel() to update respective counter (by 1) in GUI
        CREDENTIALS (dict)

    """
    while not stop_event.is_set():
        # obtain match information from FMS
        if user_data['program'] == 'FRC':
            matchesRaw = getMatchesFromFMS(user_data['season']['year'], user_data['event']['code'], 'FRC', CREDENTIALS['FRC_username'], CREDENTIALS['FRC_key'])
            matches = rewrapMatches(matchesRaw, "FRC")
        elif user_data['program'] == 'FTC':
            matchesRaw = getMatchesFromFMS(user_data['season']['year'], user_data['event']['code'], 'FTC', CREDENTIALS['FTC_username'], CREDENTIALS['FTC_key'])
            matches = rewrapMatches(matchesRaw, "FTC")
        
        # reformat into list and remove ones that are too fresh
        matches_list = [match for match in matches if (datetime.datetime.now() - match['post']).total_seconds() >= 50] # + datetime.timedelta(seconds=7*60*60)

        # determine which matches have not already been processed
        matches_new = listNotInLog('log/seek.txt', matches_list, user_data['event']['code'])

        # sent matches to builder to be generated, add them to log and count
        with open('log/seek.txt', 'a') as file:
            for match in matches_new:
                match_str = match2str(match, user_data['event']['code'])
                file.write(match_str+"\n")
                queue_build.put(match)
                incrementCountText(QLabelCounter)
                print('SEEK: '+match_str)

        # wait a little bit before looking for new matches
        time.sleep(100)

def build_video_moviepy(user_data:dict, secStart:float, secPost:float, outputFilename='output/match.mp4'):
    """
    Creates match video using moviepy from a local file

    Args:
        user_data (dict): user inputs from FRUIT GUI
            - user_data['video']['filePath'] (str): path to local video file
            - user_data['season']['secondsBeforeStart'] (float): seconds to include before match start
            - user_data['season']['secondsOfMatch'] (float): seconds to include of match play
            - user_data['season']['secondsAfterEnd'] (float): seconds to include after match end
            - user_data['season']['secondsBeforePost'] (float): seconds to include before score post
            - user_data['season']['secondsAfterPost'] (float): seconds to include after score post
        secStart (float): seconds into the video that the match starts
        secPost (float): seconds into the video that the scores post
        outputFilename (str): filename to save the output video as

    """
    with VideoFileClip(user_data['video']['filePath']) as video:
        # clip the match and the scores, adding audio fades to taste
        seg_match = video.subclipped(secStart - user_data['season']['secondsBeforeStart'], secStart + user_data['season']['secondsOfMatch'] + user_data['season']['secondsAfterEnd']).with_effects([AudioFadeIn(0.5)])
        #seg_wait = video.subclipped(secStart + user_data['season']['secondsOfMatch'] + user_data['season']['secondsAfterEnd'], secPost - user_data['season']['secondsBeforePost']).with_effects([MultiplyVolume(factor=0), MultiplySpeed(final_duration=3)])
        seg_score = video.subclipped(secPost - user_data['season']['secondsBeforePost'], secPost + user_data['season']['secondsAfterPost']).with_effects([AudioFadeOut(2)])

        # merge together match and scores
        final = concatenate_videoclips([seg_match, seg_score])

        # save the results as a file
        final.write_videofile(outputFilename, audio_codec='aac')

def build_video_ffmpeg(user_data:dict, secStart:float, secPost:float, outputFilename='output/match.mp4'):
    """
    Creates match video using ffmpeg from a local file

    Args:
        user_data (dict): user inputs from FRUIT GUI
            - user_data['video']['filePath'] (str): path to local video file
            - user_data['season']['secondsBeforeStart'] (float): seconds to include before match start
            - user_data['season']['secondsOfMatch'] (float): seconds to include of match play
            - user_data['season']['secondsAfterEnd'] (float): seconds to include after match end
            - user_data['season']['secondsBeforePost'] (float): seconds to include before score post
            - user_data['season']['secondsAfterPost'] (float): seconds to include after score post
        secStart (float): seconds into the video that the match starts
        secPost (float): seconds into the video that the scores post
        outputFilename (str): filename to save the output video as

    """
    input_file = user_data['video']['filePath']

    # Calculate timings
    match_start = secStart - user_data['season']['secondsBeforeStart']
    match_duration = (
        user_data['season']['secondsBeforeStart'] +
        user_data['season']['secondsOfMatch'] +
        user_data['season']['secondsAfterEnd'])
    score_start = secPost - user_data['season']['secondsBeforePost']
    score_duration = user_data['season']['secondsBeforePost'] + user_data['season']['secondsAfterPost']

    # Filepaths
    match_file = 'input/temp/match.mp4'
    score_file = 'input/temp/score.mp4'

    # Extract match segment with audio fades
    subprocess.run([
        'ffmpeg', '-y',
        "-loglevel", "error",
        '-ss', str(match_start),
        '-t', str(match_duration),
        '-i', input_file,
        '-af', f'afade=t=in:st=0:d=0.5,afade=t=out:st={match_duration - 1}:d=1',
        '-c:v', 'libx264',
        '-c:a', 'aac',
        str(match_file)
    ], check=True)

    # Extract score segment with audio fade out
    subprocess.run([
        'ffmpeg', '-y',
        "-loglevel", "error",
        '-ss', str(score_start),
        '-t', str(score_duration),
        '-i', input_file,
        '-af', f'afade=t=in:st=0:d=0.5,afade=t=out:st={score_duration - 2}:d=2',
        '-c:v', 'libx264',
        '-c:a', 'aac',
        str(score_file)], check=True)

    # Concatenate segments
    subprocess.run([
        "ffmpeg", "-y",
        "-loglevel", "error",
        "-f", "concat",
        "-i", "input/temp/concatenate.txt",
        "-c", "copy",
        str(outputFilename)], check=True)
    
    # Clean temp files to prevent using old ones
    if os.path.exists(match_file):
        os.remove(match_file)
    if os.path.exists(score_file):
        os.remove(score_file)

def process_queue_build_live(user_data:dict, stop_event, QLabelCounter, latestVODs:dict=VODs):
    """
    Creates match video using Twitch VOD

    Args:
        user_data (dict): user inputs from FRUIT GUI
        stop_event: (bool) or threading.Event(), used to stop processing
        QLabelCounter: PYQT QLabel() to update respective counter (by 1) in GUI
        latestVODs (dict): details of VODs found

    """
    while not stop_event.is_set():
        # if there are no Twitch stream VODs, wait a minute
        if not latestVODs:
            print('no VODs!')
            time.sleep(60)
            continue

        try:
            # grab a match from the build queue, 30 seconds wait for timeout
            match = queue_build.get(timeout=30)

            # determine which VOD contains the match
            for vod in reversed(latestVODs.values()):
                startInVideo = (match['start'] - vod['created_at']).total_seconds() < vod['duration']
                endInVideo = (match['post'] - vod['created_at']).total_seconds() < vod['duration']

                # video is in the same VOD
                if startInVideo and endInVideo:
                    break
                
                # video is in different VODs (XOR)
                if startInVideo ^ endInVideo:
                    print('bad times ahead')

                # default exit is latest VOD
                pass

            # double check VOD and match are on the same day (prevents stale)
            if (match['start'] - vod['created_at']).total_seconds() > (24*60*60):
                print('OPE! the VOD is too old for this match')
            
            # prepare VOD cut start-point
            streamVideoStartSec = ((match['start'] - vod['created_at']).total_seconds() +user_data['video']['streamDelay'] -user_data['season']['secondsBeforeStart']) #add stream delay (time from event to server) & subtract countdown

            if streamVideoStartSec < 0:
                raise ValueError("Negative start time.")

            # how many seconds into the downloaded clip the match starts
            matchStartSec = (streamVideoStartSec - int(streamVideoStartSec)) + user_data['season']['secondsBeforeStart']
            
            # prepare score post times
            postStartSec = (match['post'] - match['start']).total_seconds() + matchStartSec
            postEndDuration = (match['post'] - match['start']).total_seconds() + user_data['season']['secondsAfterPost']
            
            # convert clip timestamps to strings
            startTimestampStr = str(datetime.timedelta(seconds=(int(streamVideoStartSec))-twitch_download_pre_buffer))
            endTimestampStr = str(datetime.timedelta(seconds=(math.ceil(streamVideoStartSec+postEndDuration)+twitch_download_post_buffer)))

            # get clip from Twitch that contains both match + its score
            downloadTwitchClip(int(vod['id']), startTimestampStr, endTimestampStr, 'input/temp/twitchClip.mp4')

            # extract audio from the clip and find the exact timestamp of the match start using audio fingerprinting
            if user_data['video']['adaptiveStreamDelay']:
                extract_audio_from_mp4("input/temp/twitchClip.mp4")
                start_sound_sec, start_sound_conf = find_sound_timestamp("start.wav", "input/temp/twitchClip.wav")
                print(f"Sound found at: {start_sound_sec} seconds, with a confidence of {start_sound_conf}")

                # prepare match start and post times
                delayError = round(start_sound_sec - matchStartSec - twitch_download_pre_buffer, 5)
                matchStartSec = start_sound_sec
                postStartSec = (match['post'] - match['start']).total_seconds() + start_sound_sec

                print(f"Stream delay of {user_data['video']['streamDelay']} was adjusted by {delayError} seconds")

                # update stream delay based on audio timestamp for future matches
                user_data['video']['streamDelay'] += delayError
            else:
                # how much to trim from the start of the downloaded clip to get to the video start
                matchStartSec += twitch_download_pre_buffer

            try:
                # prepare the output filename
                outputFilename = 'output/'+match2str(match, user_data['event']['code'])+'.mp4'
                
                # build the video from the downloaded clip
                if user_data['buildMethod'] == 'moviepy':
                    build_video_moviepy(user_data, matchStartSec, postStartSec, outputFilename)
                elif user_data['buildMethod'] == 'ffmpeg':
                    build_video_ffmpeg(user_data, matchStartSec, postStartSec, outputFilename)
                
                # add the match to the send queue, update count and log
                queue_send.put(match)
                incrementCountText(QLabelCounter)
                print("BUILT: "+match2str(match, user_data['event']['code']))

            except ValueError as errorText:
                print(f'AAAHHHHHHH {errorText}')
                queue_build.put(match)
            
        except queue.Empty:
            continue
        except ValueError:
            print('negative start time, do not retry match')

def process_queue_build_static(user_data:dict, stop_event, QLabelCounter, matches, latestVODs:dict=VODs):
    """
    Creates match video using local file

    Args:
        user_data (dict): user inputs from FRUIT GUI
        stop_event: (bool) or threading.Event(), used to stop processing
        QLabelCounter: PYQT QLabel() to update respective counter (by 1) in GUI
        matches (list): list of matches from FMS
        latestVODs (dict): details of VODs found

    """

    fileDuration = VideoFileClip(user_data['video']['filePath']).duration
    fileMatchStart = [match for match in matches if match["id"] == user_data['video']['matchID']][0]['start']
    fileSecStart = (user_data['video']['matchTime'][0]*60)+user_data['video']['matchTime'][1]
    fileTimeStart = fileMatchStart-datetime.timedelta(seconds=fileSecStart)
    fileTimeEnd = fileMatchStart+datetime.timedelta(seconds=fileDuration-fileSecStart)

    while not stop_event.is_set():
        try:
            match = queue_build.get(timeout=30)

            segmentStartDatetime = match['start']-datetime.timedelta(seconds=user_data['season']['secondsBeforePost'])
            segmentEndDatetime = match['post']+datetime.timedelta(seconds=user_data['season']['secondsAfterPost'])

            if (segmentStartDatetime >= fileTimeStart)*(segmentEndDatetime < fileTimeEnd):
                # determine video timestamps of notable events
                secStart = (match['start'] - fileMatchStart).total_seconds() + fileSecStart 
                secPost = (match['post'] - fileMatchStart).total_seconds() + fileSecStart

                # prepare the output filename
                outputFilename = 'output/'+match2str(match, user_data['event']['code'])+'.mp4'

                # build the video from the downloaded clip
                if user_data['buildMethod'] == 'moviepy':
                    build_video_moviepy(user_data, secStart, secPost, outputFilename)
                elif user_data['buildMethod'] == 'ffmpeg':
                    build_video_ffmpeg(user_data, secStart, secPost, outputFilename)
                
                # add the match to the send queue, update count and log
                queue_send.put(match)
                incrementCountText(QLabelCounter)
                print("BUILT: "+match2str(match, user_data['event']['code']))
            else:
                print("NOT IN VIDEO: "+match2str(match, user_data['event']['code']))
        
        except queue.Empty:
            continue

def process_queue_send(user_data, stop_event, QLabelCounter, YouTube_Session):
    """
    Send video to YouTube and other services

    Args:
        user_data (dict): user inputs from FRUIT GUI
        stop_event: (bool) or threading.Event(), used to stop processing
        QLabelCounter: PYQT QLabel() to update respective counter (by 1) in GUI
        YouTube_Session

    """
    while not stop_event.is_set():
        try:
            match = queue_send.get(timeout=30)

            matchString = match2str(match, user_data['event']['code'])

            if YouTube_Session != None:
                # generate match thumbnail
                if user_data['program'] == 'FRC':
                    programImagePath = './images/FIRSTRobotics_IconVert_RGB.png'
                elif user_data['program'] == 'FTC':
                    programImagePath = './images/FIRSTTech_IconVert_RGB.png'
                
                if user_data['event']['forceDetails']:
                    thumbnailLoc = generateThumbnail(match, programImagePath, user_data['event']['details'], None)
                elif user_data['event']['logoSponsor'] != None:
                    thumbnailLoc = generateThumbnail(match, programImagePath, None, user_data['event']['logoSponsor'])
                else:
                    thumbnailLoc = generateThumbnail(match, programImagePath, user_data['event']['details'], None)

                title = formatYouTubeTitle(match["id"], user_data['event']['name'], user_data['season']['year']) #FTC FMS doesn't report replay?
                
                request_body = {
                    "snippet": {
                        "title": title,
                        "description": user_data['YouTube']['description'],
                        "categoryId": "28",  # Category ID for "Science & Technology"
                        "tags": user_data['YouTube']['tags'].split(',') + [user_data['event']['code'], str(user_data['season']['year']), match["id"], "FRUIT_BCC"] + [user_data['program'], {'FRC':'FIRST Robotics Competition', 'FTC':'FIRST Tech Challenge'}[user_data['program']]]
                    },
                    "status": {
                        "privacyStatus": "unlisted"
                    }
                }

                videoID = upload_video(YouTube_Session, 'output/'+matchString+'.mp4', request_body, thumbnailLoc, user_data['YouTube']['playlist'])

                if (user_data['program'] == 'FRC') and (user_data['TBA']['eventKey'] != ''):
                    data = {translateMatchString(match['id']): videoID}
                    postTheBlueAlliance(user_data['TBA']['Auth_Id'], user_data['TBA']['Auth_Secret'], user_data['TBA']['eventKey'], data)
            
            with open('log/send.txt', 'a') as file:
                file.write(matchString+"\n")
            incrementCountText(QLabelCounter)
            print("SENT: "+matchString)

        except queue.Empty:
            continue