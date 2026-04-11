from deep_translator import GoogleTranslator
import time
import concurrent.futures


def translate_texts(text_list, source_lang="ja"):
    if not text_list:
        return []

    print(f"--- ⚡ Translating {len(text_list)} lines (Google Web)... ---")
    start_time = time.time()

    # Map 'zh' to 'zh-CN' (Simplified Chinese) for Google
    if source_lang == "zh":
        source_lang = "zh-CN"

    translated_texts = []

    try:
        # We use a 'ThreadPool' to send all 5-10 lines at the exact same time.
        # This makes it feel instant (parallel processing).
        with concurrent.futures.ThreadPoolExecutor() as executor:
            translator = GoogleTranslator(source=source_lang, target='en')

            # Run all translations in parallel
            results = list(executor.map(translator.translate, text_list))

            # Clean up results
            translated_texts = [res if res else "..." for res in results]

        duration = time.time() - start_time
        print(f"--- ✅ Done in {duration:.2f}s ---")
        return translated_texts

    except Exception as e:
        print(f"❌ Translation Error: {e}")
        # Fallback: If translation fails, return the Original OCR text
        # so you can at least read the raw characters.
        return text_list