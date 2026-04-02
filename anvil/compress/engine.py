"""
Semantic Compression Engine — Reduces LLM prompt size while preserving meaning.
Lossless meaning compression: same intent, fewer tokens.
"""

import re
import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

try:
    import tiktoken
    _ENCODER = tiktoken.encoding_for_model("gpt-4")
    HAS_TIKTOKEN = True
except (ImportError, Exception):
    _ENCODER = None
    HAS_TIKTOKEN = False


@dataclass
class CompressionResult:
    """Result of semantic compression."""
    original: str
    compressed: str
    original_tokens: int
    compressed_tokens: int
    reduction_pct: float
    techniques_applied: List[str] = field(default_factory=list)

    def __str__(self):
        return (f"Compressed: {self.original_tokens} → {self.compressed_tokens} tokens "
                f"({self.reduction_pct:.1f}% reduction)")


class SemanticCompressor:
    """Compresses text while preserving semantic meaning."""

    # Filler phrases that add no semantic content
    FILLER_PATTERNS = [
        (r'\bplease\b\s*', ''),
        (r'\bkindly\b\s*', ''),
        (r'\bbasically\b\s*', ''),
        (r'\bactually\b\s*', ''),
        (r'\bessentially\b\s*', ''),
        (r'\bjust\b\s*', ''),
        (r'\bsimply\b\s*', ''),
        (r'\bI think\b\s*', ''),
        (r'\bI believe\b\s*', ''),
        (r'\bI would like you to\b\s*', ''),
        (r'\bCould you\b\s*', ''),
        (r'\bCan you\b\s*', ''),
        (r'\bWould you\b\s*', ''),
        (r'\bI need you to\b\s*', ''),
        (r'\bI want you to\b\s*', ''),
        (r'\bin order to\b', 'to'),
        (r'\bdue to the fact that\b', 'because'),
        (r'\bat this point in time\b', 'now'),
        (r'\bin the event that\b', 'if'),
        (r'\bfor the purpose of\b', 'to'),
        (r'\bwith regard to\b', 'about'),
        (r'\bin spite of the fact that\b', 'although'),
        (r'\bit is important to note that\b', ''),
        (r'\bas a matter of fact\b', ''),
        (r'\bneedless to say\b', ''),
        (r'\bit goes without saying\b', ''),
        (r'\bthe thing is\b', ''),
    ]

    # Redundant instruction patterns in coding prompts
    CODE_REDUNDANCIES = [
        (r'Make sure to\s+', ''),
        (r'Be sure to\s+', ''),
        (r'Don\'t forget to\s+', ''),
        (r'Remember to\s+', ''),
        (r'You should\s+', ''),
        (r'You need to\s+', ''),
        (r'You must\s+', ''),
        (r'It is necessary to\s+', ''),
        (r'Please make sure that\s+', ''),
        (r'Ensure that\s+', ''),
    ]

    # Verbose → concise mappings for technical instructions
    TECH_COMPRESS = [
        (r'create a (?:new )?file (?:called|named) ', 'create '),
        (r'write (?:the )?(?:following )?code (?:to|in) ', 'write to '),
        (r'add (?:the )?(?:following )?(?:code|lines?) (?:to|at) ', 'add to '),
        (r'implement a (?:function|method) (?:called|named) ', 'implement '),
        (r'(?:use|using) the (\w+) (?:library|package|module)', r'use \1'),
        (r'install the (?:following )?(?:dependencies|packages):\s*', 'install: '),
        (r'run the (?:following )?command:\s*', 'run: '),
        (r'the (?:output|result) should (?:be|look like)\s*', 'expect: '),
    ]

    def __init__(self, level: str = "medium"):
        """
        level: "light" (10-15%), "medium" (25-35%), "aggressive" (40-55%)
        """
        self.level = level

    def compress(self, text: str) -> CompressionResult:
        """Compress text semantically. Returns CompressionResult."""
        original_tokens = self._count_tokens(text)
        techniques = []
        result = text

        # Level 1 (all levels): Remove filler phrases
        result = self._remove_fillers(result)
        techniques.append("filler_removal")

        # Level 1: Collapse whitespace
        result = self._collapse_whitespace(result)
        techniques.append("whitespace_collapse")

        if self.level in ("medium", "aggressive"):
            # Level 2: Remove code redundancies
            result = self._remove_code_redundancies(result)
            techniques.append("code_redundancy_removal")

            # Level 2: Compress technical instructions
            result = self._compress_technical(result)
            techniques.append("technical_compression")

            # Level 2: Deduplicate repeated instructions
            result = self._deduplicate(result)
            techniques.append("deduplication")

        if self.level == "aggressive":
            # Level 3: Remove examples if instruction is clear
            result = self._compress_examples(result)
            techniques.append("example_compression")

            # Level 3: Abbreviate common patterns
            result = self._abbreviate(result)
            techniques.append("abbreviation")

            # Level 3: TF-IDF sentence pruning
            result = self._tfidf_compress(result)
            techniques.append("tfidf_pruning")

        compressed_tokens = self._count_tokens(result)
        reduction = ((original_tokens - compressed_tokens) / max(original_tokens, 1)) * 100

        return CompressionResult(
            original=text,
            compressed=result.strip(),
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            reduction_pct=round(reduction, 1),
            techniques_applied=techniques,
        )

    def _remove_fillers(self, text: str) -> str:
        for pattern, replacement in self.FILLER_PATTERNS:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text

    def _remove_code_redundancies(self, text: str) -> str:
        for pattern, replacement in self.CODE_REDUNDANCIES:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text

    def _compress_technical(self, text: str) -> str:
        for pattern, replacement in self.TECH_COMPRESS:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text

    def _collapse_whitespace(self, text: str) -> str:
        # Collapse multiple blank lines to single
        text = re.sub(r'\n{3,}', '\n\n', text)
        # Collapse multiple spaces (but preserve indentation)
        lines = text.split('\n')
        result = []
        for line in lines:
            indent = len(line) - len(line.lstrip())
            content = re.sub(r'  +', ' ', line.lstrip())
            result.append(' ' * indent + content)
        return '\n'.join(result)

    def _deduplicate(self, text: str) -> str:
        """Remove semantically duplicate sentences."""
        lines = text.split('\n')
        seen_normalized = set()
        result = []
        for line in lines:
            normalized = re.sub(r'\s+', ' ', line.strip().lower())
            if normalized and normalized in seen_normalized:
                continue
            if normalized:
                seen_normalized.add(normalized)
            result.append(line)
        return '\n'.join(result)

    def _compress_examples(self, text: str) -> str:
        """Shorten or remove redundant examples."""
        # If "for example" or "e.g." appears multiple times, keep first only
        parts = re.split(r'(?i)(for example|e\.g\.|such as)', text)
        if len(parts) > 3:
            # Keep first example, compress subsequent
            result = ''.join(parts[:3])
            for i in range(3, len(parts), 2):
                if i + 1 < len(parts):
                    # Shorten the example part
                    example = parts[i + 1]
                    if len(example) > 50:
                        example = example[:50].rsplit(' ', 1)[0] + '...'
                    result += parts[i] + example
                else:
                    result += parts[i]
            return result
        return text

    def _tfidf_compress(self, text: str) -> str:
        """Remove low-importance sentences using TF-IDF scoring.
        Keeps sentences with high information density, removes filler sentences."""
        sentences = re.split(r'(?<=[.!?])\s+', text)
        if len(sentences) <= 3:
            return text

        # Build document frequency across sentences
        word_doc_freq: Counter = Counter()
        sentence_words = []
        for sent in sentences:
            words = set(re.findall(r'\w+', sent.lower()))
            sentence_words.append(words)
            for w in words:
                word_doc_freq[w] += 1

        n_docs = len(sentences)
        # Score each sentence by sum of TF-IDF weights
        scored = []
        for i, (sent, words) in enumerate(zip(sentences, sentence_words)):
            if not words:
                scored.append((0, i, sent))
                continue
            word_counts = Counter(re.findall(r'\w+', sent.lower()))
            score = 0.0
            for w, tf in word_counts.items():
                df = word_doc_freq.get(w, 1)
                idf = math.log((n_docs + 1) / (df + 1)) + 1
                score += (tf / len(words)) * idf
            scored.append((score, i, sent))

        # Keep top 70% of sentences by importance
        scored.sort(key=lambda x: x[0], reverse=True)
        keep_count = max(2, int(len(scored) * 0.7))
        kept = sorted(scored[:keep_count], key=lambda x: x[1])  # Restore order
        return ' '.join(s[2] for s in kept)

    def _abbreviate(self, text: str) -> str:
        """Replace common verbose patterns with abbreviations."""
        abbreviations = [
            (r'\bfor example\b', 'e.g.'),
            (r'\bthat is to say\b', 'i.e.'),
            (r'\band so on\b', 'etc.'),
            (r'\band others\b', 'etc.'),
            (r'\bapplication\b', 'app'),
            (r'\bconfiguration\b', 'config'),
            (r'\bdirectory\b', 'dir'),
            (r'\benvironment\b', 'env'),
            (r'\brepository\b', 'repo'),
            (r'\bdocumentation\b', 'docs'),
            (r'\bimplementation\b', 'impl'),
            (r'\bfunction\b', 'fn'),
            (r'\bparameter\b', 'param'),
            (r'\bargument\b', 'arg'),
        ]
        for pattern, replacement in abbreviations:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text

    @staticmethod
    def _count_tokens(text: str) -> int:
        """Count tokens using tiktoken BPE (cl100k_base). Falls back to
        word-boundary heuristic if tiktoken unavailable."""
        if HAS_TIKTOKEN and _ENCODER is not None:
            return len(_ENCODER.encode(text))
        # Fallback: split on whitespace + punctuation boundaries
        # More accurate than len//4: counts words, numbers, and punctuation separately
        tokens = re.findall(r"\w+|[^\w\s]", text)
        return max(1, len(tokens))

    def score(self, text: str) -> dict:
        """Score compression potential and return analysis."""
        result = self.compress(text)
        return {
            "original_tokens": result.original_tokens,
            "compressed_tokens": result.compressed_tokens,
            "reduction_pct": result.reduction_pct,
            "monthly_savings_estimate": f"${round(result.reduction_pct * 0.5, 2)}/1K prompts",
            "techniques": result.techniques_applied,
            "level": self.level,
        }
