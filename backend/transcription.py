import os
import torch
import gc
import whisper
import warnings
import librosa
from speechbrain.inference.ASR import EncoderDecoderASR
from transformers import WhisperProcessor, WhisperForConditionalGeneration, pipeline, AutoTokenizer, AutoModelForSeq2SeqLM
from pydub import AudioSegment
import subprocess
import tempfile

from symspellpy.symspellpy import SymSpell
from backend.vosk_transcription import get_vosk_transcriber

warnings.filterwarnings("ignore", category=FutureWarning)

# === Konfiguration ===
USE_SPELLCHECK = True
USE_GRAMMAR = True

# === Initialisierung ===
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# SpeechBrain laden
speechbrain_model = EncoderDecoderASR.from_hparams(
    source="speechbrain/asr-crdnn-commonvoice-de",
    savedir="sb_model"
)

# Whisper Cache
loaded_whisper_models = {}

# MultiMed Whisper vorbereiten
multimed_model_path = "MultiMed-ST/asr/whisper-small-german"
if os.path.exists(multimed_model_path):
    multimed_processor = WhisperProcessor.from_pretrained(multimed_model_path)
    multimed_model = WhisperForConditionalGeneration.from_pretrained(multimed_model_path).to(DEVICE).eval()
else:
    multimed_model = None
    multimed_processor = None

# Spellcheck vorbereiten
sym_spell = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)
dictionary_path = "frequency_dictionary_med_de.txt"
if USE_SPELLCHECK and os.path.exists(dictionary_path):
    sym_spell.load_dictionary(dictionary_path, term_index=0, count_index=1)
else:
    USE_SPELLCHECK = False

# Grammatik-Modell vorbereiten
grammar_corrector = None
grammar_model_path = "local_models/grammar-correction-de"
if USE_GRAMMAR and os.path.isdir(grammar_model_path):
    grammar_tokenizer = AutoTokenizer.from_pretrained(grammar_model_path)
    grammar_model = AutoModelForSeq2SeqLM.from_pretrained(grammar_model_path)
    grammar_corrector = pipeline("text2text-generation", model=grammar_model, tokenizer=grammar_tokenizer, max_new_tokens=256)
else:
    USE_GRAMMAR = False

def spellcheck(text):
    if not USE_SPELLCHECK:
        return text, []
    suggestions = sym_spell.lookup_compound(text, max_edit_distance=2)
    if suggestions:
        corrected = suggestions[0].term
        changes = [(w1, w2) for w1, w2 in zip(text.split(), corrected.split()) if w1 != w2]
        return corrected, changes
    return text, []

def grammar_fix(text):
    if not USE_GRAMMAR:
        return text, []
    try:
        result = grammar_corrector(text)[0]['generated_text']
        changes = [(w1, w2) for w1, w2 in zip(text.split(), result.split()) if w1 != w2]
        return result, changes
    except:
        return text, []

def transcribe(model_name: str, audio_path: str) -> list[str]:
    gc.collect()
    torch.cuda.empty_cache()
    
    result_steps = []

    if model_name.startswith("Whisper"):
        model_id = model_name.split(" ")[1].lower()
        if model_id not in loaded_whisper_models:
            loaded_whisper_models[model_id] = whisper.load_model(model_id, device=DEVICE)
        model = loaded_whisper_models[model_id]
        raw_result = model.transcribe(audio_path, language="de")
        raw_text = raw_result["text"]

    elif model_name == "SpeechBrain CRDNN":
        raw_text = speechbrain_model.transcribe_file(audio_path)

    elif model_name == "MultiMed Whisper" and multimed_model:
        audio, _ = librosa.load(audio_path, sr=16000)
        input_values = multimed_processor(audio, return_tensors="pt").input_features.to(DEVICE)
        with torch.no_grad():
            predicted_ids = multimed_model.generate(input_values)
        raw_text = multimed_processor.batch_decode(predicted_ids, skip_special_tokens=True)[0]

    elif model_name == "Vosk German":
        try:
            vosk_transcriber = get_vosk_transcriber()
            raw_text = vosk_transcriber.transcribe_file(audio_path)
        except Exception as e:
            return [f"❌ Vosk Fehler: {str(e)}"]

    else:
        return ["❌ Modell nicht verfügbar"]

    result_steps.append(f"🗣 Ursprünglich: {raw_text}")

    corrected, spell_changes = spellcheck(raw_text)
    if spell_changes:
        result_steps.append(f"🪄 Rechtschreibkorrektur: {corrected}\nÄnderungen: {spell_changes}")
    else:
        result_steps.append("🪄 Keine Rechtschreibkorrekturen nötig")

    final_text, grammar_changes = grammar_fix(corrected)
    if grammar_changes:
        result_steps.append(f"🧠 Grammatik-Korrektur: {final_text}\nÄnderungen: {grammar_changes}")
    else:
        result_steps.append("🧠 Keine Grammatikänderungen nötig")

    result_steps.append(f"✅ Final: {final_text}")
    return result_steps

def transcribe_audio_chunk(model_name: str, audio_path: str, quick_mode: bool = True) -> str:
    """
    Transkribiert einen Audio-Chunk für Live-Transkription.
    Verwendet weniger Post-Processing für schnellere Ergebnisse.
    """
    gc.collect()
    torch.cuda.empty_cache()
    
    raw_text = ""
    
    try:
        if model_name.startswith("Whisper"):
            model_id = model_name.split(" ")[1].lower()
            if model_id not in loaded_whisper_models:
                loaded_whisper_models[model_id] = whisper.load_model(model_id, device=DEVICE)
            model = loaded_whisper_models[model_id]
            
            # Für Live-Transkription nutzen wir kleinere Modelle für Geschwindigkeit
            if quick_mode and model_id in ["large-v3", "medium"]:
                if "base" not in loaded_whisper_models:
                    loaded_whisper_models["base"] = whisper.load_model("base", device=DEVICE)
                model = loaded_whisper_models["base"]
            
            raw_result = model.transcribe(audio_path, language="de")
            raw_text = raw_result["text"]

        elif model_name == "SpeechBrain CRDNN":
            raw_text = speechbrain_model.transcribe_file(audio_path)

        elif model_name == "MultiMed Whisper" and multimed_model:
            # Verwende die robuste Audio-Lade-Funktion
            audio, sr = load_audio_robust(audio_path)
            input_values = multimed_processor(audio, return_tensors="pt").input_features.to(DEVICE)
            with torch.no_grad():
                predicted_ids = multimed_model.generate(input_values)
            raw_text = multimed_processor.batch_decode(predicted_ids, skip_special_tokens=True)[0]

        elif model_name == "Vosk German":
            try:
                vosk_transcriber = get_vosk_transcriber()
                raw_text = vosk_transcriber.transcribe_wav_chunk(audio_path)
            except Exception as e:
                return f"❌ Vosk Chunk Fehler: {str(e)}"

        else:
            return "❌ Modell nicht verfügbar"

        # Im Quick-Mode nur minimale Korrektur
        if quick_mode:
            # Nur Spellcheck, keine Grammatikkorrektur für Geschwindigkeit
            corrected, _ = spellcheck(raw_text)
            return corrected.strip()
        else:
            # Vollständige Verarbeitung
            corrected, _ = spellcheck(raw_text)
            final_text, _ = grammar_fix(corrected)
            return final_text.strip()
            
    except Exception as e:
        print(f"Transcription error in transcribe_audio_chunk: {e}")
        return f"❌ Fehler bei der Transkription: {str(e)}"

def convert_audio_to_wav(input_path: str, output_path: str) -> bool:
    """
    Konvertiert Audio-Dateien zu WAV-Format für bessere Kompatibilität
    """
    try:
        # Versuche zuerst mit pydub
        audio = AudioSegment.from_file(input_path)
        audio = audio.set_frame_rate(16000).set_channels(1)  # Mono, 16kHz
        audio.export(output_path, format="wav")
        return True
    except Exception as e:
        print(f"pydub conversion failed: {e}")
        try:
            # Fallback mit ffmpeg direkt
            subprocess.run([
                'ffmpeg', '-i', input_path, 
                '-ar', '16000', '-ac', '1', 
                '-y', output_path
            ], check=True, capture_output=True)
            return True
        except Exception as e2:
            print(f"ffmpeg conversion failed: {e2}")
            return False

def load_audio_robust(audio_path: str):
    """
    Lädt Audio-Dateien robust mit mehreren Fallbacks
    """
    try:
        # Versuche direktes Laden mit librosa
        audio, sr = librosa.load(audio_path, sr=16000)
        return audio, sr
    except Exception as e:
        print(f"Direct librosa load failed: {e}")
        
        # Erstelle temporäre WAV-Datei
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            temp_wav = tmp.name
        
        try:
            if convert_audio_to_wav(audio_path, temp_wav):
                audio, sr = librosa.load(temp_wav, sr=16000)
                os.unlink(temp_wav)  # Lösche temporäre Datei
                return audio, sr
        except Exception as e2:
            print(f"Conversion and load failed: {e2}")
        finally:
            if os.path.exists(temp_wav):
                os.unlink(temp_wav)
        
        raise Exception(f"Could not load audio file: {audio_path}")
