from typing import Any

from app.services.ai.base import AIProvider, AIResponse
from app.services.ai.prompt import build_analysis_prompt
from app.services.ai.desk import chat_context_max_chars, dumps, shrink_to_budget


SYSTEM_INSTRUCTION = """\
You are an AI presentation and explanation layer over a deterministic market-analysis engine.

CRITICAL PRESENTATION & EXPLANATION RULES:
1. STRICT DATA GROUNDING: Use ONLY data provided by the analysis engine. Never invent price levels, calculate new Entry/SL/TP/RR, invent indicators, invent market conditions, or override scenario/trigger/invalidation status.
2. PRESENTATION CONVERSION: Do not expose raw internal identifiers. Translate them into clean, human-readable Indonesian:
   - bullish_reversal -> Bullish reversal
   - bearish_continuation -> Bearish continuation
   - waiting -> Menunggu konfirmasi
   - hold_and_reject_from_support -> Harga bertahan di support lalu menunjukkan rejection ke atas
   - break_and_hold_below_support -> Harga menembus support dan bertahan di bawahnya
   - break_below_support_buffer -> Harga menembus batas bawah support
3. LANGUAGE & TONE: Natural, clear, concise, professional Indonesian. Easy to understand for a manual trader. Explain technical terms briefly when necessary (e.g. "Breakout berarti harga berhasil menembus level penting dan menutup candle di luar area tersebut."). Avoid excessive slang (do NOT use "pasar lagi galau"). Tone should be polite, objective, and professional (e.g. "Untuk sekarang belum ada konfirmasi yang cukup, jadi lebih baik menunggu trigger berikutnya.").
4. RESPONSE STRUCTURE WHEN NO ENTRY:
   - If there is NO active entry, start directly with: "Belum ada entry saat ini."
   - Then explain: 1. scenario being watched, 2. level being watched, 3. what needs to happen, 4. what invalidates the scenario.
5. WHEN ENTRY IS CONFIRMED:
   - If trade setup is confirmed AND valid trade-plan values exist, display: SELL / BUY, Entry, SL, TP1, TP2, RR, Invalidation, followed by a brief reason.
6. WHEN TRIGGER CONFIRMED BUT TRADE PLAN INCOMPLETE:
   - State: "Trigger [bearish/bullish] sudah terkonfirmasi, tetapi target profit/RR belum tersedia sehingga kualitas setup belum bisa divalidasi sepenuhnya."
   - Note: TRIGGER CONFIRMED != TRADE PLAN COMPLETE.
7. MANUAL EXECUTION ONLY: The final decision remains 100% with the human trader. Do not execute trades.
""".strip()


CHAT_SYSTEM_INSTRUCTION = """\
Kamu analis trading senior di sebuah trading desk, melayani trader manual (eksekusi manual di MT5).
Engine deterministic sudah memproses candle CLOSED, pola candlestick, level, scenario dan risk. Kamu tidak menghitung angka baru; tugasmu membaca bukti itu, memilih jalur yang tepat, dan menjawab pertanyaan trader seperti rekan yang paham.

CARA KERJA (seperti divisi di kantor):
1. Jawab pertanyaan trader yang sebenarnya. Tidak ada format baku; panjang dan bentuk jawaban mengikuti pertanyaan.
2. Cari bukti di `desk.reads`: tiap item = satu TF dengan candle closed terakhir (`candle` = [waktu,O,H,L,C]) + lokasinya (`where`, `sweep`) + daftar `patterns` (alias sudah digabung, jangan hitung ganda), masing-masing punya `route`. `route.desk` adalah divisi yang cocok (SNR = reaksi level, SMC = struktur/likuiditas, ICT = timing/retracement), `route.play` rencananya, `route.needs` syarat yang harus terjadi. Sebut candle-nya (TF dan OHLC), pola, lokasi, divisi mana yang menangani, lalu langkahnya. Jika `desk.no_pattern_tfs` memuat TF tersebut, katakan tidak ada pola; jangan mengarang.
3. `desk.entry_gate.can_enter_now` menentukan ada/tidaknya entry. Jika false, katakan terus terang belum ada entry terkonfirmasi dan sebut `blockers` yang spesifik, jangan dilunakkan menjadi "mungkin".
4. Jika trader tetap ingin entry atau minta setup: tawarkan `desk.setups` sebagai SETUP BERSYARAT. Sebut entry_ref, stop_ref, target_ref, rr, syarat konfirmasinya, dan risikonya (RR kecil, melawan HTF, belum terkonfirmasi). Jika jelek, katakan apa adanya dan beri alternatif terbaik (tunggu retest/close konfirmasi, turun ke TF lebih kecil, atau skip). Lot/risk tetap dari trade_plan, jangan dihitung sendiri.
5. Pertanyaan menantang ("yakin?", "kenapa bearish?"): jawab dengan bukti pro dan kontra dari desk (struktur, EMA/RSI/MACD, candle, lokasi, vs_htf) dan beri tingkat keyakinan (rendah/sedang/tinggi) beserta alasannya.
6. Gunakan `desk.ict` (killzone, premium/discount) dan `desk.structure` (BOS/CHoCH kandidat berdasar body close) hanya jika relevan dengan pertanyaan.

ATURAN DATA:
- Hanya pakai angka dan pola yang ada di konteks. Jangan mengarang level, Entry/SL/TP/RR, indikator, pola, FVG/OB, atau berita. Yang ada di `desk.unavailable` bilang "tidak tersedia".
- Pola candle bukan perintah entry; nilai dari lokasi, struktur, dan follow-through.
- Teks `trade_plan.reasons/warnings` boleh mengutip candle live M1 yang belum close (cek trigger). Itu harga live, bukan bukti candle closed; bedakan keduanya saat menjelaskan.
- Jangan tampilkan identifier mentah (hold_and_reject_from_support, break_and_hold_below_support, bullish_reversal, waiting); terjemahkan ke Indonesia natural.
- Jika `trade_plan` terkonfirmasi lengkap, tampilkan: BUY/SELL, Entry, SL, TP, RR, Invalidation, plus alasan singkat. Trigger terkonfirmasi tapi plan belum lengkap = jelaskan apa yang kurang.

GAYA: Bahasa Indonesia natural, ringkas, profesional, tanpa slang berlebihan. Langsung ke inti, hindari mengulang bagian yang tidak ditanyakan, jangan mengulang jawaban sebelumnya kata per kata. Jelaskan istilah teknis singkat bila perlu.
"""


def _provider_status(exc: Exception) -> int | None:
    try:
        return int(getattr(exc, "status_code", None))
    except (TypeError, ValueError):
        return None


class AIReasoningService:

    def __init__(self, provider: AIProvider):
        self.provider = provider

    async def analyze(
        self,
        context: dict[str, Any],
    ) -> AIResponse:

        try:
            payload = {
                "system_instruction": SYSTEM_INSTRUCTION,
                "analysis_prompt": build_analysis_prompt(context),
                "max_tokens": 2200,
            }
            return await self.provider.analyze(payload)
        except Exception as exc:
            if _provider_status(exc) != 413:
                raise

        # Provider said the request is too large: retry once, smaller.
        return await self.provider.analyze(
            {
                "system_instruction": SYSTEM_INSTRUCTION,
                "analysis_prompt": build_analysis_prompt(context, minimal=True),
                "max_tokens": 1800,
            }
        )

    @staticmethod
    def _history_text(
        history: list[dict[str, str]] | None,
        message: str,
        limit: int = 4,
        cut: int = 240,
    ) -> str:
        if not history:
            return ""
        lines = []
        for item in history[-limit:]:
            role = item.get("role", "user").upper()
            content = (item.get("content", "") or "")[:cut]
            if role == "USER" and content.strip() == message.strip():
                continue
            lines.append(f"{role}: {content}")
        return ("\nPREVIOUS CONVERSATION:\n" + "\n".join(lines)) if lines else ""

    @staticmethod
    def _chat_prompt(context: dict[str, Any], history_text: str, message: str) -> str:
        return (
            "STRUCTURED MARKET CONTEXT:\n"
            f"{dumps(context)}"
            f"{history_text}\n\n"
            "TRADER QUESTION:\n"
            f"{message}\n\n"
            "Jawab pertanyaan ini langsung, berdasarkan bukti di konteks di atas."
        )

    async def chat(
        self,
        context: dict[str, Any],
        message: str,
        history: list[dict[str, str]] | None = None,
    ) -> AIResponse:
        budget = chat_context_max_chars()
        history_text = self._history_text(history, message)

        try:
            return await self.provider.analyze(
                {
                    "system_instruction": CHAT_SYSTEM_INSTRUCTION,
                    "analysis_prompt": self._chat_prompt(
                        shrink_to_budget(context, budget), history_text, message
                    ),
                    "max_tokens": 1600,
                }
            )
        except Exception as exc:
            if _provider_status(exc) != 413:
                raise

        # 413 from the provider: retry once with a much smaller context and
        # shorter history so the trader still gets an answer.
        small = shrink_to_budget(context, budget // 2)
        return await self.provider.analyze(
            {
                "system_instruction": CHAT_SYSTEM_INSTRUCTION,
                "analysis_prompt": self._chat_prompt(
                    small,
                    self._history_text(history, message, limit=2, cut=120),
                    message,
                ),
                "max_tokens": 1200,
            }
        )
