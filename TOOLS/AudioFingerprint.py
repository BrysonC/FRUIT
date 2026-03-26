import subprocess
import numpy as np
from scipy.io import wavfile
from scipy.signal import correlate

def extract_audio_from_mp4(mp4_path: str, target_sr: int = 11025):
    """Extract mono WAV audio from an MP4 file using ffmpeg.

    Args:
        mp4_path: Path to the input MP4 video file.
        wav_path: Path where the extracted WAV audio will be written.
        target_sr: Desired sample rate for the output WAV file.
    """
    wav_path = mp4_path.replace(".mp4", ".wav")

    cmd = [
        "ffmpeg", 
        "-y",
        "-i", mp4_path,
        "-ac", "1",
        "-ar", str(target_sr),
        "-vn", "-copyts",
        wav_path,
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

def find_sound_timestamp(ref_wav, video_wav, video_crop_start_sec=0, video_crop_end_sec=None):
    """Find the timestamp of a reference sound within a video's audio track.

    Args:
        ref_wav: Path to the reference WAV file containing the sound to find.
        video_wav: Path to the WAV file extracted from the video.
        video_crop_sec: Optional [start, end] seconds to crop the video audio for faster processing.
    
    Returns:
        Timestamp (in seconds) where the reference sound best matches within the video audio.
        Confidence score of the match (0 to 1, higher is better; typically 0.3-0.6).
    """
    # Load reference sound
    sr_ref, ref = wavfile.read(ref_wav)
    ref = ref.astype(np.float32)
    ref /= np.max(np.abs(ref))

    # Load video audio
    sr_vid, vid = wavfile.read(video_wav)
    vid = vid.astype(np.float32)
    vid /= np.max(np.abs(vid))

    # Crop video audio if provided
    if (video_crop_end_sec is not None):
        if video_crop_start_sec < 0 or video_crop_end_sec > len(vid) / sr_vid or video_crop_start_sec >= video_crop_end_sec:
            raise ValueError("Crop times must be within the duration of the video audio.")
        else:
            crop_start_sample = int(video_crop_start_sec * sr_vid)
            crop_end_sample = int(video_crop_end_sec * sr_vid)

            vid = vid[crop_start_sample:crop_end_sample]

    # Ensure sample rates match
    if sr_ref != sr_vid:
        raise ValueError(f"Sample rates differ: {sr_ref} vs {sr_vid}")

    # Cross-correlation
    corr = correlate(vid, ref, mode='valid')
    best_index = np.argmax(corr)
    best_value = corr[best_index]

    # Compute normalization factor for confidence
    ref_energy = np.linalg.norm(ref)
    vid_energy = np.linalg.norm(vid[best_index : best_index + len(ref)])
    confidence = np.sqrt(best_value / (ref_energy * vid_energy))

    # Convert index → seconds
    timestamp_seconds = (best_index / sr_vid) + video_crop_start_sec

    return round(timestamp_seconds,5), round(confidence, 4)