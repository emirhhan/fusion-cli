using System;
using System.Globalization;
using System.Speech.Recognition;
using System.Text;
using System.Threading;
using System.Diagnostics;

namespace FusionListen
{
    internal static class Program
    {
        private const double MinimumConfidence = 0.2;
        private const int MinimumSpeechMs = 250;
        private static readonly ManualResetEvent Done = new ManualResetEvent(false);
        private static readonly object Gate = new object();
        private static readonly Stopwatch SpeechClock = new Stopwatch();
        private static SpeechRecognitionEngine recognizer;
        private static bool stopping;
        private static int exitCode;
        private static bool speechActive;
        private static int segment;

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

        private static void StartSpeech()
        {
            if (speechActive) return;
            speechActive = true;
            segment += 1;
            SpeechClock.Restart();
            WriteEvent("ses-basladi", string.Empty, null, 0, segment);
        }

        private static bool Qualified(string text, double confidence, int speechMs)
        {
            return speechActive && text.Length > 0 && confidence >= MinimumConfidence
                && speechMs >= MinimumSpeechMs;
        }

        private static void EndSpeech(int speechMs)
        {
            if (!speechActive) return;
            speechActive = false;
            SpeechClock.Stop();
            WriteEvent("ses-bitti", string.Empty, null, speechMs, segment);
        }

        private static int RunFixture(string locale, string fixture)
        {
            WriteEvent("hazir", locale);
            if (fixture == "silence") return 0;

            StartSpeech();
            int speechMs = fixture == "too-short" ? 120 : 320;
            double confidence = fixture == "low-confidence" ? 0.1 : 0.82;
            string text = "merhaba";
            if (Qualified(text, confidence, speechMs))
            {
                WriteEvent("kismi", text, confidence, speechMs, segment);
                WriteEvent("son", text, confidence, speechMs, segment);
            }
            else
            {
                WriteEvent("hata", "Güvenilir konuşma tanınamadı.", null, speechMs, segment);
            }
            EndSpeech(speechMs);
            return 0;
        }

        private static int Main(string[] args)
        {
            Console.OutputEncoding = new UTF8Encoding(false);
            string locale = args.Length > 0 ? args[0] : "tr-TR";
            if (args.Length > 2 && args[1] == "--fixture")
            {
                return RunFixture(locale, args[2]);
            }
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
                recognizer.SpeechDetected += (_, __) => StartSpeech();
                recognizer.SpeechHypothesized += (_, eventArgs) =>
                {
                    string text = eventArgs.Result?.Text ?? string.Empty;
                    int speechMs = (int)SpeechClock.ElapsedMilliseconds;
                    if (Qualified(text, eventArgs.Result.Confidence, speechMs))
                    {
                        WriteEvent("kismi", text, eventArgs.Result.Confidence, speechMs, segment);
                    }
                };
                recognizer.SpeechRecognized += (_, eventArgs) =>
                {
                    string text = eventArgs.Result?.Text ?? string.Empty;
                    int speechMs = Math.Max(
                        (int)SpeechClock.ElapsedMilliseconds,
                        eventArgs.Result.Audio == null ? 0 : (int)eventArgs.Result.Audio.Duration.TotalMilliseconds
                    );
                    if (!Qualified(text, eventArgs.Result.Confidence, speechMs))
                    {
                        WriteEvent("hata", "Güvenilir konuşma tanınamadı.", null, speechMs, segment);
                        EndSpeech(speechMs);
                        Finish(0);
                        return;
                    }
                    WriteEvent("son", text, eventArgs.Result.Confidence, speechMs, segment);
                    EndSpeech(speechMs);
                    Finish(0);
                };
                recognizer.SpeechRecognitionRejected += (_, __) =>
                {
                    int speechMs = (int)SpeechClock.ElapsedMilliseconds;
                    WriteEvent("hata", "Konuşma anlaşılamadı.", null, speechMs, segment);
                    EndSpeech(speechMs);
                    Finish(0);
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
