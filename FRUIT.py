# imports for GUI
from PyQt6.QtWidgets import (QApplication, QWidget,  QFormLayout, QGridLayout, QTabWidget, QPushButton, QLineEdit, QPlainTextEdit, QLabel, QFileDialog, QComboBox, QCheckBox, QHBoxLayout, QStackedWidget, QVBoxLayout, QCompleter)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtGui import QPixmap, QColor
from PyQt6.QtCore import QSize, QUrl, QTimer
from PyQt6.QtSvgWidgets import QSvgWidget

import random       # random thumbnail generation
import datetime     # str conversion and timeDelta
import pytz         # timezone handling
import os           # file IO
import json         # CONFIG handling

# my functions, see python scripts in TOOLS
from TOOLS.CredentialsPopUp import CredDialog
from TOOLS.FMS import getMatchesFromFMS
from TOOLS.FMS import rewrapMatches
from TOOLS.FMS import getEventInfoFromFMS
from TOOLS.timezones import convert_windows_to_iana
from TOOLS.YouTube import authenticate_youtube
from TOOLS.thumbnails import generateThumbnail
from TOOLS.TBA import postTheBlueAlliance
from TOOLS.Twitch import covertID2Username
from TOOLS.YoutubeLivestream import getChannelIDFromHandle

# processes to run on queued threads
import threading
from TOOLS.process_queue import watch
from TOOLS.process_queue import process_queue_seek
from TOOLS.process_queue import process_queue_build_live
from TOOLS.process_queue import process_queue_build_static
from TOOLS.process_queue import process_queue_send
from TOOLS.ffmpegrecord import start_recording
from TOOLS.ffmpegrecord import stop_recording

# create directories/files if missing
os.makedirs('log/', exist_ok=True)
open('log/seek.txt', 'a+').close()
open('log/send.txt', 'a+').close()
os.makedirs('input/temp', exist_ok=True)
os.makedirs('output/thumbnails', exist_ok=True)

# translator for symbols
translateSymbol = {'M': 'Playoffs', 'P': 'Playoffs', 'Q': 'Quals', 'F': 'Finals'}

class MainWindow(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        #prepare optional arguments
        self.logoSponsorFilepath = None
        self.videoFilepath = None
        self.twitchUserID = None
        self.youtubeUserID = None
        self.YouTube = None
        self.stop_event = threading.Event()

        '''
        set window title, size and layout
        '''
        self.setWindowTitle('FRUIT by Bryce Castle')
        self.setGeometry(250, 250, 800, 400)
        main_layout = QGridLayout(self)
        self.setLayout(main_layout)
        self.tab = QTabWidget(self)

        '''
        WELCOME PAGE
         - information on how to use tool
         - mostly text
        '''
        bodyText = "<ol style='font-size: 16px !important;'><li><b>Event Info</b>: used to obtain match details from FMS, learn more at https://frc-events.firstinspires.org/services/api</li><li>Connect to your YouTube account using the browser. Define <b>YouTube Settings</b> for video upload.</li><li>Supply <b>Thumbnail Info</b> and test its generation.</li><li>Set <b>Match Timing</b> offsets, relative to match start and scores post (in seconds).</li><li>Select the <b>Video Input</b> source to be trimmed.</li><li>Connect to <b>The Blue Alliance</b> for match video visibility.</li><li><b>Bake CONFIG</b> to save on future re-entry time.</li><li>Click the <b>Make The Sauce</b> button to get everything rolling!"

        page_welcome = QWidget(self)
        layout = QFormLayout()
        page_welcome.setLayout(layout)
        layout.addRow(QLabel("<h1>FIRST Robotics Uploader from an Indiana Teammate</h1>\n<i>Make each tab green then you're ready to proceed.</i>"))
        layout.addRow(QLabel(bodyText))
        # set/check credentials via dialog pop-up window
        self.credentialsButton = QPushButton("Set/Check Credentials", self)
        self.credentialsButton.clicked.connect(lambda: CredDialog(self).exec())
        layout.addRow(self.credentialsButton)

        '''
        EVENT PAGE
         - Program (FRC/FTC)
         - Season Year
         - Event Code
         - Event Name & Timezone
         - Pull from FMS
        '''
        page_event = QWidget(self)
        layout = QFormLayout()
        page_event.setLayout(layout)
        # select program (FRC/FTC)
        self.program = QComboBox(); self.program.addItems(["FRC", "FTC"])
        layout.addRow(QLabel("Select program:"), self.program)
        # Event (Season) Year
        self.season_year = QComboBox(); self.season_year.addItems(["2026", "2025", "2024"])
        layout.addRow(QLabel('Season Year:'), self.season_year)
        # Event Code
        self.event_code = QLineEdit(self);
        layout.addRow(QLabel('Event Code:'), self.event_code)
        # FMS pull button
        self.textFMS = QLabel('<font color="red">Event not yet pulled</font>')
        self.button_FMS = QPushButton('Pull FMS')
        self.button_FMS.clicked.connect(lambda: self.handleFMS(self.season_year.currentText(), self.event_code.text().upper()))
        layout.addRow(self.button_FMS, self.textFMS)
        # Event Name
        self.event_name = QLineEdit(self);
        layout.addRow(QLabel('Event Name:'), self.event_name)
        # Event Timezone
        self.event_timezone = QComboBox(); self.event_timezone.setEditable(True)
        completerTimezone = QCompleter(pytz.all_timezones); self.event_timezone.setCompleter(completerTimezone)
        layout.addRow(QLabel('Event Timezone:'), self.event_timezone)
        

        '''
        YOUTUBE PAGE
         - YouTube Authentication
         - YouTube video description, tags, playlist
        '''
        page_YouTube = QWidget(self)
        layout = QFormLayout()
        page_YouTube.setLayout(layout)
        layout.addRow(QLabel('<b>Connect the YouTube channel you want to upload to, accepting both permissions (read & write videos)</b>'))
        # Authentication
        self.textYouTube = QLabel('<font color="red">YouTube not yet authenticated</font>')
        self.button_FMS = QPushButton('Connect to YouTube')
        self.button_FMS.clicked.connect(self.handleYouTube)
        layout.addRow(self.button_FMS, self.textYouTube)
        # Playlist
        self.video_playlist = QLineEdit("https://www.youtube.com/playlist?list=")
        layout.addRow('Playlist URL (optional):', self.video_playlist)
        # Description
        self.video_description = QPlainTextEdit("Footage of this event is courtesy of FIRST Indiana Robotics.\n\nFollow us:\nhttps://twitch.tv/firstinrobotics\nhttps://www.facebook.com/FIRSTINRobotics/\nhttps://www.instagram.com/firstinrobotics/\nhttps://www.linkedin.com/company/first-in-robotics/\n\nEvent pictures: https://www.flickr.com/photos/indianafirst/albums/\n\nFor more information and future event schedules, visit our website: https://www.firstindianarobotics.org")
        layout.addRow('Description:', self.video_description)
        # Tags
        self.video_tags = QLineEdit('FIRST Indiana Robotics, FIN')
        layout.addRow(QLabel('Tags (comma-delimited) :'), self.video_tags)
        layout.addRow(QLabel('<i>program will automatically add year, event code, and program (FRC/FTC)</i>'))
        
        '''
        THUMBNAIL PAGE
         - Sponsor Image
         - Verbose event details
         - Random thumbnail generator
        '''
        page_thumbnail = QWidget(self)
        layout = QFormLayout()
        page_thumbnail.setLayout(layout)
        layout.addRow(QLabel('<b>Choose a sponsor logo OR fill out more event info for YouTube thumbnail</b>'))
        # Sponsor Image
        self.img_EventSponsor = QPushButton('Select File')
        self.img_EventSponsor.clicked.connect(lambda: self.getFileSponsorImage(self.img_EventSponsor))
        layout.addRow('Sponsor Logo:', self.img_EventSponsor)
        # Verbose event details
        layout.addRow(QLabel('⸻ or ⸻'))
        self.eventBuilding = QLineEdit(self);  layout.addRow('Building:', self.eventBuilding)
        self.eventCity = QLineEdit(self);  layout.addRow('City:', self.eventCity)
        self.eventDates = QLineEdit(self);  layout.addRow('Dates:', self.eventDates)
        # Force text details over sponsor logo
        self.thumbnail_force = QCheckBox('Force using additional event info')
        layout.addRow(self.thumbnail_force)
        # Test thumbnail using random generator
        self.image_thumbnail = QLabel('<font color="red">Generate a test thumbnail</font>')
        self.button_thumbnail = QPushButton('Test Thumbnail')
        self.button_thumbnail.clicked.connect(lambda: self.handleThumbnail([self.eventBuilding.text(), self.eventCity.text(), self.eventDates.text()], self.image_thumbnail, self.thumbnail_force.isChecked()))
        layout.addRow(self.button_thumbnail, self.image_thumbnail)

        '''
        TIMINGS PAGE
         - seconds before match starts (to hear MC countdown)
         - match duration (auto + buzzer + teleop)
         - seconds to show after end of game
         - seconds to wait after post (reval animation)
         - seconds to show score
        '''
        page_timings = QWidget(self)
        layout = QFormLayout()
        page_timings.setLayout(layout)
        layout.addRow(QLabel('<b>Define how to chop up the livestream into matches</b><br><i>Units are in seconds, decimals allowed.</i>'))
        #2024 FRC values: [3, 155, 5, -7.25, 16.67]
        #2025 FRC values: [6, 155, 8, -8.06, 33]
        self.season_secondsBefore = QLineEdit(str(3.94)); layout.addRow('Before Match :', self.season_secondsBefore)
        self.season_matchDuration = QLineEdit(str(20+5+140)); layout.addRow('Match Duration :', self.season_matchDuration)
        self.season_secondsAfterEnd = QLineEdit(str(3+2)); layout.addRow('After Match :', self.season_secondsAfterEnd)
        self.season_secondsBeforePost = QLineEdit(str(-5.8)); layout.addRow('Before Post :', self.season_secondsBeforePost)
        self.season_secondsAfterPost = QLineEdit(str(20+5.8)); layout.addRow('After Post :', self.season_secondsAfterPost)
        layout.addRow(QLabel('<i>These should add to 179.94 to get a 3:00 video on YouTube</i>'))
        svg_widget = QSvgWidget('./images/matchTrimDiagram.svg')
        svg_widget.setFixedSize(QSize(600, 150))
        layout.addRow(svg_widget)

        '''
        VIDEO INPUT
         - select video input (live/static)
         - provide reference match (# and time)
         - watch 4 seconds of clip
        '''
        page_video = QWidget(self)
        layout = QVBoxLayout()
        page_video.setLayout(layout)

        # Dropdown to switch views
        self.dropdownInput = QComboBox()
        self.dropdownBuildMethod = QComboBox()
        self.stacked_widget = QStackedWidget()
        self.dropdownInput.addItems(["Twitch Livestream", "Static File", "YouTube Livestream (experimental)"])
        self.dropdownBuildMethod.addItems(["ffmpeg", "moviepy"])
        self.dropdownInput.currentIndexChanged.connect(lambda index: self.stacked_widget.setCurrentIndex(index))
        layout.addWidget(self.dropdownInput)
        layout.addWidget(self.dropdownBuildMethod)
        layout.addWidget(self.stacked_widget)

        # Video Input 1: Twitch Livestream
        video_input_Twitch = QFormLayout()
        self.twitchUser = QLineEdit('firstinrobotics'); video_input_Twitch.addRow('Twitch User:', self.twitchUser)
        self.twitch_button = QPushButton("Test Twitch Connection")
        self.twitch_button.setStyleSheet('color: red')
        self.twitch_button.clicked.connect(self.test_twitch)
        video_input_Twitch.addRow(self.twitch_button)
        self.streamDelay = QLineEdit("4")
        video_input_Twitch.addRow("Stream Delay [sec] (increase if late):", self.streamDelay)
        self.adaptiveStreamDelayCheckbox = QCheckBox('Adaptive stream delay')
        self.adaptiveStreamDelayCheckbox.setChecked(True)
        video_input_Twitch.addRow(self.adaptiveStreamDelayCheckbox)
        Twitch_widget = QWidget()
        Twitch_widget.setLayout(video_input_Twitch)
        self.stacked_widget.addWidget(Twitch_widget)

        # Video Input 2: Static File
        video_input_File = QFormLayout()
        self.mp4_VOD = QPushButton("Select File")
        self.mp4_VOD.clicked.connect(self.getFileVideo)
        video_input_File.addRow('Video File:', self.mp4_VOD)
        # reference match details
        self.match_type = QComboBox(); self.match_type.addItems(["Q = Quals", "P = Playoffs", "F = Finals"])
        video_input_File.addRow('First Match Type:', self.match_type)
        self.match_number_ref = QLineEdit(); video_input_File.addRow('First Match Number:', self.match_number_ref)
        self.timestamp_input = QLineEdit(); video_input_File.addRow('Enter timestamp (mm:ss):', self.timestamp_input)
        # Create a video widget and add it to the layout
        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumSize(480, 270)
        self.play_button = QPushButton("Play 4 Seconds")
        self.play_button.setStyleSheet('color: red')
        self.play_button.clicked.connect(self.play_video)
        video_input_File.addRow(self.play_button, self.video_widget)
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)
        file_widget = QWidget()
        file_widget.setLayout(video_input_File)
        self.stacked_widget.addWidget(file_widget)

        # Video Input 3: YouTube Livestream
        video_input_YouTube = QFormLayout()
        self.youtubeUser = QLineEdit("FIRSTINRobotics"); video_input_YouTube.addRow("Youtube Username:", self.youtubeUser)
        # gets channel ID from username
        self.youtube_button = QPushButton("Test YouTube Livestream Connection")
        video_input_YouTube.addRow(self.youtube_button)
        self.youtube_button.setStyleSheet("color: red")
        self.youtube_button.clicked.connect(self.get_yt_channel_ID)
        self.record_button = QPushButton(
            "Start Recording YouTube Livestream! (Polls every ten seconds to see if channel is live)"
        )
        video_input_YouTube.addRow(self.record_button)
        self.record_button.setStyleSheet("color: red")
        self.record_button.clicked.connect(lambda: start_recording(self.youtubeUserID))
        self.record_button.clicked.connect(self.recording_button)
        self.stop_button = QPushButton("Stop Recording YouTube Livestream.")
        video_input_YouTube.addRow(self.stop_button)
        self.stop_button.setStyleSheet("color: red")
        self.stop_button.clicked.connect(stop_recording)
        YouTube_widget = QWidget()
        YouTube_widget.setLayout(video_input_YouTube)
        self.stacked_widget.addWidget(YouTube_widget)

        '''
        TBA PAGE
         - Season Year
         - Event Code & Name
         - Pull from FMS
        '''
        page_TBA = QWidget(self)
        layout = QFormLayout()
        page_TBA.setLayout(layout)

        self.TBA_eventCode = QLineEdit(); layout.addRow(QLabel('TBA event code:'), self.TBA_eventCode)
        self.TBA_AuthID = QLineEdit(); layout.addRow(QLabel('Associated Auth ID:'), self.TBA_AuthID)
        self.TBA_AuthSecret = QLineEdit(); layout.addRow(QLabel('Associated Auth Secret:'), self.TBA_AuthSecret)
        
        # FMS pull button
        self.button_TBA = QPushButton("Verify TBA"); self.button_TBA.setStyleSheet('color: red')
        self.button_TBA.clicked.connect(lambda: self.handleTBA(self.TBA_AuthID.text(), self.TBA_AuthSecret.text(), self.TBA_eventCode.text()))
        layout.addRow(self.button_TBA)

        '''
        add all tabs to window
        '''
        self.tab.addTab(page_welcome, 'Welcome')
        self.tab.addTab(page_event, 'Event Info')
        self.tab.addTab(page_YouTube, 'YouTube Settings')
        self.tab.addTab(page_thumbnail, 'Thumbnail Info')
        self.tab.addTab(page_timings, 'Match Timing')
        self.tab.addTab(page_video, 'Video Input')
        self.tab.addTab(page_TBA, 'The Blue Alliance')
        # set tab colors
        self.tab.tabBar().setTabTextColor(1, QColor('red'))
        self.tab.tabBar().setTabTextColor(2, QColor('red'))
        self.tab.tabBar().setTabTextColor(3, QColor('red'))
        self.tab.tabBar().setTabTextColor(4, QColor('green'))
        self.tab.tabBar().setTabTextColor(5, QColor('red'))
        self.tab.tabBar().setTabTextColor(6, QColor('red'))
        main_layout.addWidget(self.tab)

        '''
        Bake CONFIG button
        '''
        config_container = QWidget()
        config_layout = QHBoxLayout(config_container)
        self.load_config = QPushButton('Load CONFIG')
        self.load_config.clicked.connect(lambda: self.loadCONFIG(self.load_config))
        config_layout.addWidget(self.load_config)
        self.bake_config = QPushButton('Bake CONFIG')
        self.bake_config.clicked.connect(lambda: self.bakeCONFIG(self.bake_config))
        config_layout.addWidget(self.bake_config)
        main_layout.addWidget(config_container)

        self.startThreadButton = QPushButton('Make The Sauce')
        self.startThreadButton.clicked.connect(self.start_sauce_thread)
        main_layout.addWidget(self.startThreadButton)

        '''
        Status Bar (SEEN, BUILT, SENT)
        '''
        status_container = QWidget()
        status_layout = QHBoxLayout(status_container)
        
        self.status_seen = QLabel(" SEEN: X")
        self.status_built = QLabel("BUILT: X")
        self.status_sent = QLabel(" SENT: X")
        
        status_layout.addWidget(self.status_seen)
        status_layout.addWidget(self.status_built)
        status_layout.addWidget(self.status_sent)

        main_layout.addWidget(status_container)

        self.show()
    
    def start_sauce_thread(self):
        # disable the button to prevent double-click
        self.startThreadButton.setEnabled(False)

        # clear the stop event
        self.stop_event.clear()

        # Clear and entries in send log file that were not finished
        with open('log/send.txt', 'r') as source_file, open('log/seek.txt', 'w') as destination_file:
            # Read the contents of the source file and write them to the destination file
            destination_file.write(source_file.read())
        
        with open('log/send.txt', 'r') as file:
            # Count finished matches
            count_finished = len([line for line in file if self.CONFIG['event']['code'] in line])

        self.status_seen.setText(f" SEEN: {count_finished}")
        self.status_built.setText(f"BUILT: {count_finished}")
        self.status_sent.setText(f" SENT: {count_finished}")

        # load API credentials
        with open("CREDENTIALS", "r") as file:
            CREDENTIALS = json.load(file)

        # Create threads for each queue
        self.thread_seek = threading.Thread(target=process_queue_seek, args=(self.CONFIG, self.stop_event, self.status_seen, CREDENTIALS))
        if self.CONFIG['video']['type'].startswith('live'):
            self.thread_build = threading.Thread(target=process_queue_build_live, args=(self.CONFIG, self.stop_event, self.status_built))
        elif self.CONFIG['video']['type'] == 'static':
            self.thread_build = threading.Thread(target=process_queue_build_static, args=(self.CONFIG, self.stop_event, self.status_built, self.matches))
        self.thread_send = threading.Thread(target=process_queue_send, args=(self.CONFIG, self.stop_event, self.status_sent, self.YouTube))

        # Start the threads
        if self.CONFIG['video']['type'].startswith('live'):
            watch(self.CONFIG['video']['twitchUserID'], self.stop_event, CREDENTIALS)
        self.thread_seek.start()
        self.thread_build.start()
        self.thread_send.start()

    def on_sauce_made(self, result):
        self.startThreadButton.setText(f"{result} matches processed!")
        self.startThreadButton.setEnabled(True)
    
    def play_video(self):
        # Get the timestamp from the input field and convert it to milliseconds
        timestamp = self.timestamp_input.text()
        self.match_timeMin, self.match_timeSec = map(float, timestamp.split(':'))
        position = int((self.match_timeMin * 60 + self.match_timeSec) * 1000)
        self.media_player.setPosition(position)
        self.media_player.play()

        # Pause the video after 4 seconds
        QTimer.singleShot(4000, self.media_player.pause)
        self.tab.tabBar().setTabTextColor(5, QColor('green'))
        self.play_button.setStyleSheet('color: green')
    
    def getFileVideo(self, button):
        response = QFileDialog.getOpenFileName(
            parent=self,
            caption='Select a file',
            directory=os.getcwd(),
            filter='Video File (*.mp4)'
        )
        
        self.videoFilepath = response[0]
        
        self.mp4_VOD.setText('📁'+response[0].split('/')[-1])
        self.media_player.setSource(QUrl.fromLocalFile(response[0]))
    
    def getFileSponsorImage(self, button):
        response = QFileDialog.getOpenFileName(
            parent=self,
            caption='Select a file',
            directory=os.getcwd(),
            filter='Image File (*.png *.jpg)'
        )

        self.logoSponsorFilepath = response[0]

        button.setText('📁'+response[0].split('/')[-1])
    
    def handleFMS(self, year, eventCode):
        self.textFMS.setText('<font color="aqua">Loading event from FMS...</font>')
        self.textFMS.repaint()

        with open("CREDENTIALS", "r") as file:
            CREDENTIALS = json.load(file) # contains API credentials
        
        try:
            if self.program.currentText() == 'FRC':
                matchesRaw = getMatchesFromFMS(year, eventCode, self.program.currentText(), CREDENTIALS['FRC_username'], CREDENTIALS['FRC_key'])
                eventInfo = getEventInfoFromFMS(year, eventCode, self.program.currentText(), CREDENTIALS['FRC_username'], CREDENTIALS['FRC_key'])
                eventInfo['timezone'] = convert_windows_to_iana(eventInfo['timezone'])
            elif self.program.currentText() == 'FTC':
                matchesRaw = getMatchesFromFMS(year, eventCode, self.program.currentText(), CREDENTIALS['FTC_username'], CREDENTIALS['FTC_key'])
                eventInfo = getEventInfoFromFMS(year, eventCode, self.program.currentText(), CREDENTIALS['FTC_username'], CREDENTIALS['FTC_key'])
            
            self.matches = rewrapMatches(matchesRaw, self.program.currentText())
            
            # Report success of FMS pull
            if len(self.matches) != 0:
                self.textFMS.setText('<font color="green">'+str(len(self.matches))+' matches found for '+eventCode+'.</font>')
            else:
                self.textFMS.setText('<font color="yellow">No matches found for '+eventCode+'. If event has begun, verify event code.</font>')
            
            # Update status bar counters
            self.status_seen.setText(f" SEEN: {len(self.matches)}")
            with open('log/send.txt', 'r') as file:
                eventMatchesSent = len([line.strip() for line in file if line.startswith(eventCode.upper())])
            self.status_built.setText(f"BUILT: {eventMatchesSent}")
            self.status_sent.setText(f" SENT: {eventMatchesSent}")

            # Update event fields if empty
            if self.event_name.text() == '':
                self.event_name.setText(eventInfo['name'])
            if self.event_timezone.currentText() == '':
                self.event_timezone.setCurrentText(eventInfo['timezone'])
            if self.eventBuilding.text() == '':
                self.eventBuilding.setText(eventInfo['venue'])
            if self.eventCity.text() == '':
                self.eventCity.setText(eventInfo['city']+', '+eventInfo['stateprov'])
            if self.eventDates.text() == '':
                startDate = datetime.datetime.fromisoformat(eventInfo['dateStart']).date()
                endDate = datetime.datetime.fromisoformat(eventInfo['dateEnd']).date()
                if startDate == endDate:
                    self.eventDates.setText(startDate.strftime("%m/%d/%Y"))
                else:
                    self.eventDates.setText(f'{startDate.month}/{startDate.day}-{endDate.day}/{endDate.year}')

            self.tab.tabBar().setTabTextColor(1, QColor('green'))
        except json.JSONDecodeError:
            self.textFMS.setText('<font color="red">Event does not exist!</font>')
            self.tab.tabBar().setTabTextColor(1, QColor('red'))
    
    def test_twitch(self):
        
        self.twitch_button.setText('Looking for Twitch user...')
        self.twitch_button.setStyleSheet("color: aqua;")
        self.twitch_button.repaint()

        with open("CREDENTIALS", "r") as file:
            CREDENTIALS = json.load(file) # contains API credentials
        
        try:
            self.twitchUserID = covertID2Username(CREDENTIALS['Twitch_clientID'], CREDENTIALS['Twitch_clientSecret'], self.twitchUser.text())
            self.twitch_button.setText('User found! ID:'+ self.twitchUserID)
            self.twitch_button.setStyleSheet("color: green;")
            self.tab.tabBar().setTabTextColor(5, QColor('green'))
        except IndexError:
            self.twitch_button.setText("Twitch user not found!")
            self.twitch_button.setStyleSheet("color: red;")
            self.tab.tabBar().setTabTextColor(5, QColor('red'))

    def get_yt_channel_ID(self):
        self.youtube_button.setText("Looking for Youtube user...")
        self.youtube_button.setStyleSheet("color: aqua;")
        self.youtube_button.repaint()
        with open("CREDENTIALS", "r") as file:
            CREDENTIALS = json.load(file)  # contains API credentials
        try:
            self.youtubeUserID = getChannelIDFromHandle(self.youtubeUser.text())
            self.youtube_button.setText("User ID Found!")
            self.youtube_button.setStyleSheet("color: green")
            self.tab.tabBar().setTabTextColor(5, QColor("green"))
        except IndexError:
            self.youtube_button.setText("YouTube user not found!")
            self.youtube_button.setStyleSheet("color: red")

    def recording_button(self):
        self.record_button.setText("Looking for/recording livestream... check ./TOOLS/recordings/ for video file!")
        self.record_button.setStyleSheet("color: aqua;")
        self.youtube_button.repaint()

    def handleTBA(self, TBA_Auth_Id, TBA_Auth_Secret, TBA_eventKey):
        self.button_TBA.setText('Testing TBA API...')
        self.button_TBA.setStyleSheet('color: aqua')
        self.button_TBA.repaint()

        response = postTheBlueAlliance(TBA_Auth_Id, TBA_Auth_Secret, TBA_eventKey)

        if response.status_code == 200:
            self.button_TBA.setText('TBA API Verified!')
            self.button_TBA.setStyleSheet('color: green')
            self.button_TBA.repaint()
            self.tab.tabBar().setTabTextColor(6, QColor('green'))
        else:
            self.button_TBA.setText('Issue with TBA API!')
            self.button_TBA.setStyleSheet('color: red')
            self.button_TBA.repaint()
    
    def handleYouTube(self):
        self.textYouTube.setText('<font color="aqua">Authenticate using browser...</font>')
        self.textYouTube.repaint()

        self.YouTube = authenticate_youtube()
        self.textYouTube.setText('<font color="green">YouTube authenticated!</font>')
        self.tab.tabBar().setTabTextColor(2, QColor('green'))
    
    def handleThumbnail(self, data, image, forceText = False):
        image.setText('<font color="aqua">Generating thumbnail...</font>')
        image.repaint()

        typMatchNumb = {'Q':70, 'P':13, 'F':3}
        matchType = random.choices(['Q', 'P', 'F'], [0.8, 0.15, 0.05])[0]
        matchNum = random.randint(1, typMatchNumb[matchType])

        teams = [random.randint(1, 11000) for x in range(6)]
        matchInfo = {'id': matchType+str(matchNum), 'start':datetime.datetime.now(), 'post': datetime.datetime.now()+datetime.timedelta(seconds=155), 'teamsRed': teams[0:3], 'teamsBlue' : teams[3:6]}

        eventDetails = data[0]+"\n"+data[1]+"\n"+data[2]

        if self.program.currentText() == 'FRC':
            programImagePath = './images/FIRSTRobotics_IconVert_RGB.png'
        elif self.program.currentText() == 'FTC':
            programImagePath = './images/FIRSTTech_IconVert_RGB.png'

        if forceText:
            generateThumbnail(matchInfo, programImagePath, eventDetails, None, './images/trial')
        elif self.logoSponsorFilepath != None:
            generateThumbnail(matchInfo, programImagePath, None, self.logoSponsorFilepath, './images/trial')
        else:
            generateThumbnail(matchInfo, programImagePath, eventDetails, None, './images/trial')
        
        image.setPixmap(QPixmap('./images/trial.png').scaled(QSize(424, 240)))
        self.tab.tabBar().setTabTextColor(3, QColor('green'))
    
    def bakeCONFIG(self, button):
        try:

            original_text = button.text()
            original_style = button.styleSheet()

            # Sets text and color back to default so users know config can be baked again without restarting program
            QTimer.singleShot(
                2000,
                lambda: (
                    button.setStyleSheet(original_style),
                    button.setText(original_text),
                ),
            )

            CONFIG = {
                'program' : self.program.currentText(),
                'event' : {
                    'code' : self.event_code.text().upper(),
                    'name' : self.event_name.text(),
                    'timezone' : self.event_timezone.currentText(),
                    'details' : self.eventBuilding.text()+'\n'+self.eventCity.text()+'\n'+self.eventDates.text(),
                    'logoSponsor' : self.logoSponsorFilepath,
                    'forceDetails' : bool(self.thumbnail_force.isChecked())
                },
                'season' : {
                    'year' : int(self.season_year.currentText()),
                    'secondsBeforeStart' : float(self.season_secondsBefore.text()),
                    'secondsOfMatch' : float(self.season_matchDuration.text()), #auto + bell (~5) + teleop
                    'secondsAfterEnd' : float(self.season_secondsAfterEnd.text()),
                    'secondsBeforePost' : float(self.season_secondsBeforePost.text()),
                    'secondsAfterPost' : float(self.season_secondsAfterPost.text())
                },
                'YouTube' : {
                    'description' : self.video_description.toPlainText(),
                    'tags' : self.video_tags.text(),
                    'playlist' : self.video_playlist.text().split('?list=')[-1]
                },
                'TBA' : {
                    'Auth_Id' : self.TBA_AuthID.text(),
                    'Auth_Secret': self.TBA_AuthSecret.text(),
                    'eventKey': self.TBA_eventCode.text()
                }
            }

            CONFIG['buildMethod'] = self.dropdownBuildMethod.currentText()

            if 'twitch' in self.dropdownInput.currentText().lower():
                CONFIG['video'] = {'type': 'live_twitch', 
                                   'twitchUsername' : self.twitchUser.text(),
                                   'twitchUserID' : self.twitchUserID, 
                                   'streamDelay' : float(self.streamDelay.text()),
                                   'adaptiveStreamDelay' : bool(self.adaptiveStreamDelayCheckbox.isChecked()),
                                   'filePath' : 'input/temp/twitchClip.mp4'}
            elif 'youtube' in self.dropdownInput.currentText().lower():
                CONFIG['video'] = {'type': 'live_youtube', 
                                   'youtubeUsername' : self.youtubeUser.text(),
                                   'youtubeUserID' : self.youtubeUserID, 
                                   'streamDelay' : float(self.streamDelay.text()),
                                   'filePath' : 'input/temp/youtubeClip.mp4',
                                   'recordingStartTime': 'TODO: add start time feature'}
            elif 'static' in self.dropdownInput.currentText().lower():
                CONFIG['video'] = {'type': 'static',
                                   'filePath' : self.videoFilepath,
                                   'matchID' : self.match_type.currentText()[0] + self.match_number_ref.text(),
                                   'matchTime' : (self.match_timeMin, self.match_timeSec)}
            
            self.CONFIG = CONFIG

            with open("CONFIG", "w") as file:
                json.dump(CONFIG, file, indent=2)
            button.setStyleSheet('color: green')
            button.setText('Bake CONFIG: SUCCESS!')
        
        except AttributeError:
            button.setStyleSheet('color: red')
            button.setText('Bake CONFIG: ERROR')
    
    def loadCONFIG(self, button):
        response = QFileDialog.getOpenFileName(
            parent=self,
            caption='Select a file',
            directory=os.getcwd(),
            filter='CONFIG File (*CONFIG)'
        )

        if response[0]!='':
            button.setText('📁'+response[0].split('/')[-1])
            
            with open(response[0], "r") as file:
                CONFIG = json.load(file)
            
                self.program.setCurrentText(CONFIG['program'])

                self.event_code.setText(CONFIG['event']['code'])
                self.event_name.setText(CONFIG['event']['name'])
                self.event_timezone.setCurrentText(CONFIG['event']['timezone'])
                eventDetails = CONFIG['event']['details'].split('\n')
                self.eventBuilding.setText(eventDetails[0])
                self.eventCity.setText(eventDetails[1])
                self.eventDates.setText(eventDetails[2])
                self.logoSponsorFilepath = CONFIG['event']['logoSponsor']
                if self.logoSponsorFilepath != None:
                    self.img_EventSponsor.setText('📁'+self.logoSponsorFilepath.split('/')[-1])
                self.thumbnail_force.setChecked(CONFIG['event']['forceDetails'])

                self.season_year.setCurrentText(str(CONFIG['season']['year']))
                self.season_secondsBefore.setText(str(CONFIG['season']['secondsBeforeStart']))
                self.season_matchDuration.setText(str(CONFIG['season']['secondsOfMatch']))
                self.season_secondsAfterEnd.setText(str(CONFIG['season']['secondsAfterEnd']))
                self.season_secondsBeforePost.setText(str(CONFIG['season']['secondsBeforePost']))
                self.season_secondsAfterPost.setText(str(CONFIG['season']['secondsAfterPost']))

                self.video_description.setPlainText(CONFIG['YouTube']['description'])
                self.video_tags.setText(CONFIG['YouTube']['tags'])
                self.video_playlist.setText('https://www.youtube.com/playlist?list='+CONFIG['YouTube']['playlist'])

                self.TBA_AuthID.setText(CONFIG['TBA']['Auth_Id'])
                self.TBA_AuthSecret.setText(CONFIG['TBA']['Auth_Secret'])
                self.TBA_eventCode.setText(CONFIG['TBA']['eventKey'])

                self.dropdownBuildMethod.setCurrentText(CONFIG['buildMethod'])
                
                if CONFIG['video']['type'] == 'static':
                    self.videoFilepath = CONFIG['video']['filePath']
                    if CONFIG['video']['filePath'] != None:
                        self.mp4_VOD.setText('📁'+CONFIG['video']['filePath'].split('/')[-1])
                        self.media_player.setSource(QUrl.fromLocalFile(CONFIG['video']['filePath']))
                    self.match_type.setCurrentText({'Q':"Q = Quals", 'P':"P = Playoffs", 'F':"F = Finals"}[CONFIG['video']['matchID'][0]])
                    self.match_number_ref.setText(CONFIG['video']['matchID'][1:])
                    self.match_timeMin = CONFIG['video']['matchTime'][0]
                    self.match_timeSec = CONFIG['video']['matchTime'][1]
                    self.timestamp_input.setText(str(self.match_timeMin)+':'+str(self.match_timeSec))
                    self.dropdownInput.setCurrentText("Static File")
                elif CONFIG['video']['type'].startswith('live'):
                    self.streamDelay.setText(str(CONFIG['video']['streamDelay']))
                    if CONFIG['video']['type'].endswith('twitch'):
                        self.adaptiveStreamDelayCheckbox.setChecked(CONFIG['video']['adaptiveStreamDelay'])
                        self.twitchUser.setText(CONFIG['video']['twitchUsername'])
                        self.dropdownInput.setCurrentText("Twitch Livestream")
                        if CONFIG['video']['twitchUserID'] is not None:
                            self.twitchUserID = CONFIG['video']['twitchUserID']
                    elif CONFIG['video']['type'].endswith('youtube'):
                        self.youtubeUser.setText(CONFIG['video']['youtubeUsername'])
                        self.youtubeUserID = CONFIG['video']['youtubeUserID']
                        self.dropdownInput.setCurrentText("YouTube Livestream (experimental)")
        else:
            print('No CONFIG selected!')

import sys
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    sys.exit(app.exec())