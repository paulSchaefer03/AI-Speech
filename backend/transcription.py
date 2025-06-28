import os
import torch
import gc
import whisper
import warnings
import librosa
from speechbrain.inference.ASR import EncoderDecoderASR
from transformers import WhisperProcessor, WhisperForConditionalGeneration, pipeline, AutoTokenizer, AutoModelForSeq2SeqLM

from symspellpy.symspellpy import SymSpell

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
