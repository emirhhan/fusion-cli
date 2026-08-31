using System;
using System.Globalization;
using System.Speech.Recognition;
using System.Text;
using System.Threading;

namespace FusionListen
{
    internal static class Program
    {
        private static readonly ManualResetEvent Done = new ManualResetEvent(false);
        private static readonly object Gate = new object();
        private static SpeechRecognitionEngine recognizer;
        private static bool stopping;
        private static int exitCode;

        private static string JsonEscape(string value)
        {
            var result = new StringBuilder(value.Length + 16);
            foreach (char character in value)
            {
                switch (character)
                {
                    case '"': result.Append("\\\""); break;
                    case '\\': result.Append("\\\\"); break;
                    case '\b': result.Append("\\b"); break;
                    case '\f': result.Append("\\f"); break;
                    case '\n': result.Append("\\n"); break;
                    case '\r': result.Append("\\r"); break;
                    case '\t': result.Append("\\t"); break;
                    default:
                        if (character < 0x20)
                        {
                            result.Append("\\u");
                            result.Append(((int)character).ToString("x4", CultureInfo.InvariantCulture));
                        }
                        else
                        {
                            result.Append(character);
                        }
                        break;
                }
            }
            return result.ToString();
        }

        private static void WriteEvent(
            string kind,
            string text,
            double? confidence = null,
            int speechMs = 0,
            int segment = 0
        )
        {
            string confidenceJson = confidence.HasValue
                ? confidence.Value.ToString("R", CultureInfo.InvariantCulture)
                : "null";
            Console.WriteLine(
                "{\"tur\":\"" + JsonEscape(kind) +
                "\",\"metin\":\"" + JsonEscape(text) +
                "\",\"guven\":" + confidenceJson +
                ",\"speech_ms\":" + speechMs.ToString(CultureInfo.InvariantCulture) +
                ",\"segment\":" + segment.ToString(CultureInfo.InvariantCulture) + "}"
            );
            Console.Out.Flush();
        }

        private static void Finish(int code)
        {
            lock (Gate)
            {
                if (stopping) return;
                stopping = true;
                exitCode = code;
                Done.Set();
            }
        }

        private static bool IsStopping()
        {
            lock (Gate) return stopping;
        }

        private static int Main(string[] args)
        {
            Console.OutputEncoding = new UTF8Encoding(false);
            string locale = args.Length > 0 ? args[0] : "tr-TR";
            try
            {
                recognizer = new SpeechRecognitionEngine(new CultureInfo(locale));
            }
            catch (Exception error) when (error is ArgumentException || error is InvalidOperationException)
            {
                WriteEvent("hata", "Bu dil için Windows konuşma tanıyıcısı bulunamadı: " + locale);
                return 2;
            }

            Console.CancelKeyPress += (_, eventArgs) =>
            {
                eventArgs.Cancel = true;
                Finish(0);
            };

            try
            {
                recognizer.LoadGrammar(new DictationGrammar());
                recognizer.SpeechHypothesized += (_, eventArgs) =>
                {
                    string text = eventArgs.Result?.Text ?? string.Empty;
                    if (text.Length > 0) WriteEvent("kismi", text, eventArgs.Result.Confidence);
                };
                recognizer.SpeechRecognized += (_, eventArgs) =>
                {
                    string text = eventArgs.Result?.Text ?? string.Empty;
                    if (text.Length == 0)
                    {
                        WriteEvent("hata", "Konuşma anlaşılamadı.");
                        Finish(5);
                        return;
                    }
                    WriteEvent("son", text, eventArgs.Result.Confidence);
                    Finish(0);
                };
                recognizer.SpeechRecognitionRejected += (_, __) =>
                {
                    WriteEvent("hata", "Konuşma anlaşılamadı.");
                    Finish(5);
                };
                recognizer.RecognizeCompleted += (_, eventArgs) =>
                {
                    if (eventArgs.Error != null)
                    {
                        WriteEvent("hata", "Windows konuşma tanıma hatası: " + eventArgs.Error.Message);
                        Finish(5);
                    }
                    else if (!IsStopping())
                    {
                        WriteEvent("hata", "Konuşma tanıma sonuç üretmeden sonlandı.");
                        Finish(5);
                    }
                };

                recognizer.SetInputToDefaultAudioDevice();
                recognizer.RecognizeAsync(RecognizeMode.Single);
                WriteEvent("hazir", locale);
                Done.WaitOne();
                return exitCode;
            }
            catch (Exception error)
            {
                WriteEvent("hata", "Windows konuşma tanıma başlatılamadı: " + error.Message);
                return 4;
            }
            finally
            {
                try { recognizer.RecognizeAsyncCancel(); } catch (InvalidOperationException) { }
                try { recognizer.SetInputToNull(); } catch (InvalidOperationException) { }
                recognizer.Dispose();
            }
        }
    }
}
