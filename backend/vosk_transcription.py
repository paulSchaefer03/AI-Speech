"""
Vosk-based real-time speech-to-text transcription module.
Optimized for continuous/streaming recognition of German speech.
"""

import json
import os
import wave
import vosk
import queue
import threading
import time
from typing import Optional, Callable, Dict, Any
import gc

# Model path configuration
VOSK_MODEL_PATH = "/home/paul-schaefer/Dokumente/Klinikum_Fulda/Spech_to_Text_Demo/vosk-model-de-tuda-0.6-900k"

class VoskTranscriber:
    """
    Real-time transcriber using Vosk for German speech recognition.
    Supports both single-shot transcription and continuous streaming.
    """
    
    def __init__(self, model_path: str = VOSK_MODEL_PATH, sample_rate: int = 16000):
        self.model_path = model_path
        self.sample_rate = sample_rate
        self.model = None
        self.recognizer = None
        # Lazy loading - Modell wird erst beim ersten Gebrauch geladen
    
    def _load_model(self):
        """Load the Vosk model."""
        if self.model is not None:
            return  # Bereits geladen
            
        try:
            if not os.path.exists(self.model_path):
                raise FileNotFoundError(f"Vosk model not found at {self.model_path}")
            
            print(f"Loading Vosk model from {self.model_path}")
            self.model = vosk.Model(self.model_path)
            self.recognizer = vosk.KaldiRecognizer(self.model, self.sample_rate)
            
            # Enable word-level timestamps and confidence scores
            self.recognizer.SetWords(True)
            
            print("Vosk model loaded successfully")
            
        except Exception as e:
            print(f"Error loading Vosk model: {e}")
            raise
    
    def transcribe_file(self, audio_path: str) -> str:
        """
        Transcribe a complete audio file.
        
        Args:
            audio_path: Path to the audio file
            
        Returns:
            Transcribed text
        """
        self._load_model()  # Lazy loading
        
        try:
            # Open wave file
            with wave.open(audio_path, 'rb') as wf:
                # Validate audio format
                if wf.getframerate() != self.sample_rate:
                    print(f"Warning: Audio sample rate {wf.getframerate()} differs from expected {self.sample_rate}")
                
                if wf.getnchannels() != 1:
                    print(f"Warning: Audio has {wf.getnchannels()} channels, expected 1 (mono)")
                
                # Create a new recognizer for this transcription
                rec = vosk.KaldiRecognizer(self.model, wf.getframerate())
                rec.SetWords(True)
                
                # Process audio in chunks
                results = []
                while True:
                    data = wf.readframes(4000)
                    if len(data) == 0:
                        break
                    
                    if rec.AcceptWaveform(data):
                        result = json.loads(rec.Result())
                        if result.get('text'):
                            results.append(result['text'])
                
                # Get final result
                final_result = json.loads(rec.FinalResult())
                if final_result.get('text'):
                    results.append(final_result['text'])
                
                # Join all results
                full_text = ' '.join(results).strip()
                return full_text if full_text else ""
                
        except Exception as e:
            print(f"Error transcribing file {audio_path}: {e}")
            return f"❌ Vosk transcription error: {str(e)}"
    
    def transcribe_chunk(self, audio_data: bytes) -> Dict[str, Any]:
        """
        Transcribe an audio chunk for real-time processing.
        
        Args:
            audio_data: Raw audio bytes (16-bit PCM)
            
        Returns:
            Dictionary with transcription result and metadata
        """
        self._load_model()  # Lazy loading
        
        try:
            # Create a new recognizer for this chunk
            rec = vosk.KaldiRecognizer(self.model, self.sample_rate)
            rec.SetWords(True)
            
            # Process the audio data
            if rec.AcceptWaveform(audio_data):
                result = json.loads(rec.Result())
                return {
                    'text': result.get('text', ''),
                    'confidence': result.get('conf', 0.0),
                    'words': result.get('result', []),
                    'partial': False
                }
            else:
                # Get partial result
                partial_result = json.loads(rec.PartialResult())
                return {
                    'text': partial_result.get('partial', ''),
                    'confidence': 0.0,
                    'words': [],
                    'partial': True
                }
                
        except Exception as e:
            print(f"Error transcribing chunk: {e}")
            return {
                'text': f"❌ Vosk chunk error: {str(e)}",
                'confidence': 0.0,
                'words': [],
                'partial': False
            }
    
    def transcribe_wav_chunk(self, wav_path: str) -> str:
        """
        Transcribe a WAV file chunk for real-time processing.
        Optimized for speed in live transcription scenarios.
        
        Args:
            wav_path: Path to the WAV file chunk
            
        Returns:
            Transcribed text
        """
        self._load_model()  # Lazy loading
        
        try:
            with wave.open(wav_path, 'rb') as wf:
                # Read all audio data
                audio_data = wf.readframes(wf.getnframes())
                
                # Create a new recognizer for this chunk
                rec = vosk.KaldiRecognizer(self.model, wf.getframerate())
                
                # Process the entire chunk at once
                if rec.AcceptWaveform(audio_data):
                    result = json.loads(rec.Result())
                    text = result.get('text', '')
                else:
                    # If not enough data for final result, get partial
                    rec.AcceptWaveform(audio_data)
                    final_result = json.loads(rec.FinalResult())
                    text = final_result.get('text', '')
                
                return text.strip()
                
        except Exception as e:
            print(f"Error transcribing WAV chunk {wav_path}: {e}")
            return ""

class VoskStreamTranscriber:
    """
    Streaming transcriber for continuous real-time recognition.
    """
    
    def __init__(self, model_path: str = VOSK_MODEL_PATH, sample_rate: int = 16000):
        self.model_path = model_path
        self.sample_rate = sample_rate
        self.model = None
        self.recognizer = None
        self.audio_queue = queue.Queue()
        self.result_queue = queue.Queue()
        self.is_running = False
        self.worker_thread = None
        # Lazy loading - Modell wird erst beim ersten Start geladen
    
    def _load_model(self):
        """Load the Vosk model."""
        if self.model is not None:
            return  # Bereits geladen
            
        try:
            if not os.path.exists(self.model_path):
                raise FileNotFoundError(f"Vosk model not found at {self.model_path}")
            
            print(f"Loading Vosk streaming model from {self.model_path}")
            self.model = vosk.Model(self.model_path)
            self.recognizer = vosk.KaldiRecognizer(self.model, self.sample_rate)
            self.recognizer.SetWords(True)
            
            print("Vosk streaming model loaded successfully")
            
        except Exception as e:
            print(f"Error loading Vosk streaming model: {e}")
            raise
    
    def start_streaming(self, result_callback: Optional[Callable] = None):
        """
        Start the streaming transcription worker.
        
        Args:
            result_callback: Optional callback function for results
        """
        if self.is_running:
            return
        
        self._load_model()  # Lazy loading beim ersten Start
        
        self.is_running = True
        self.worker_thread = threading.Thread(
            target=self._stream_worker,
            args=(result_callback,)
        )
        self.worker_thread.start()
        print("Vosk streaming started")
    
    def stop_streaming(self):
        """Stop the streaming transcription worker."""
        self.is_running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=2.0)
        print("Vosk streaming stopped")
    
    def add_audio_chunk(self, audio_data: bytes):
        """
        Add audio data to the processing queue.
        
        Args:
            audio_data: Raw audio bytes (16-bit PCM)
        """
        if self.is_running:
            self.audio_queue.put(audio_data)
    
    def get_result(self, timeout: float = 0.1) -> Optional[Dict[str, Any]]:
        """
        Get the next transcription result.
        
        Args:
            timeout: Timeout in seconds
            
        Returns:
            Transcription result or None if no result available
        """
        try:
            return self.result_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def _stream_worker(self, result_callback: Optional[Callable]):
        """Worker thread for processing audio stream."""
        print("Vosk stream worker started")
        
        while self.is_running:
            try:
                # Get audio data from queue
                audio_data = self.audio_queue.get(timeout=0.1)
                print(f"Processing audio chunk in worker: {len(audio_data)} bytes")
                
                # Process with Vosk
                try:
                    if self.recognizer.AcceptWaveform(audio_data):
                        result = json.loads(self.recognizer.Result())
                        print(f"Vosk AcceptWaveform returned result: {result}")
                        
                        if result.get('text'):
                            result_dict = {
                                'text': result['text'],
                                'confidence': result.get('conf', 0.0),
                                'words': result.get('result', []),
                                'partial': False,
                                'timestamp': time.time()
                            }
                            
                            print(f"Vosk final result: {result_dict}")
                            
                            # Add to result queue
                            self.result_queue.put(result_dict)
                            
                            # Call callback if provided
                            if result_callback:
                                try:
                                    result_callback(result_dict)
                                except Exception as e:
                                    print(f"Error in result callback: {e}")
                    
                    # Always get partial result to show intermediate progress
                    partial_result = json.loads(self.recognizer.PartialResult())
                    print(f"Vosk PartialResult returned: {partial_result}")
                    
                    if partial_result.get('partial'):
                        result_dict = {
                            'text': partial_result['partial'],
                            'confidence': 0.0,
                            'words': [],
                            'partial': True,
                            'timestamp': time.time()
                        }
                        
                        print(f"Vosk partial result: {result_dict}")
                        
                        # Add to result queue
                        self.result_queue.put(result_dict)
                        
                        # Call callback if provided
                        if result_callback:
                            try:
                                result_callback(result_dict)
                            except Exception as e:
                                print(f"Error in partial result callback: {e}")
                                
                except Exception as vosk_error:
                    print(f"Vosk processing error: {vosk_error}")
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error in streaming worker: {e}")
        
        print("Vosk stream worker ended")
    
    def __del__(self):
        """Cleanup when object is destroyed."""
        self.stop_streaming()

# Global instances for reuse
_vosk_transcriber = None
_vosk_stream_transcriber = None

def get_vosk_transcriber() -> VoskTranscriber:
    """Get or create the global Vosk transcriber instance."""
    global _vosk_transcriber
    if _vosk_transcriber is None:
        _vosk_transcriber = VoskTranscriber()
    return _vosk_transcriber

def get_vosk_stream_transcriber() -> VoskStreamTranscriber:
    """Get or create the global Vosk stream transcriber instance."""
    global _vosk_stream_transcriber
    if _vosk_stream_transcriber is None:
        _vosk_stream_transcriber = VoskStreamTranscriber()
    return _vosk_stream_transcriber

def cleanup_vosk_resources():
    """Cleanup Vosk resources."""
    global _vosk_transcriber, _vosk_stream_transcriber
    
    if _vosk_stream_transcriber:
        _vosk_stream_transcriber.stop_streaming()
        _vosk_stream_transcriber = None
    
    if _vosk_transcriber:
        _vosk_transcriber = None
    
    gc.collect()
    print("Vosk resources cleaned up")
