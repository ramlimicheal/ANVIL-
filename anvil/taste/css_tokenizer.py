"""
CSS Tokenizer — Proper lexical analysis for CSS verification.
Eliminates false positives from regex matching inside comments, strings, URLs.

Tradeoff vs PostCSS: PostCSS is Node.js-only and handles SCSS/CSS-in-JS nesting.
This tokenizer handles standard CSS + Tailwind @apply correctly. For SCSS/Less,
a future upgrade would use tree-sitter-css or a PostCSS bridge.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from enum import Enum, auto


class TokenType(Enum):
    SELECTOR = auto()
    PROPERTY = auto()
    VALUE = auto()
    COMMENT = auto()
    STRING = auto()
    URL = auto()
    AT_RULE = auto()
    OPEN_BRACE = auto()
    CLOSE_BRACE = auto()
    SEMICOLON = auto()
    WHITESPACE = auto()


@dataclass
class CSSToken:
    """A single token from CSS lexing."""
    type: TokenType
    value: str
    line: int
    col: int


@dataclass
class CSSDeclaration:
    """A parsed property: value pair from real CSS (not from comments/strings)."""
    property: str
    value: str
    line: int
    selector: str = ""


@dataclass
class CSSRule:
    """A complete CSS rule: selector { declarations }."""
    selector: str
    declarations: List[CSSDeclaration]
    line: int


class CSSTokenizer:
    """Lexer + parser for CSS that correctly handles comments, strings, and URLs.
    
    The key upgrade over regex: colors/values found inside /* comments */,
    "strings", url(...), or data: URIs are correctly excluded from verification.
    """

    def __init__(self, code: str):
        self.code = code
        self.pos = 0
        self.line = 1
        self.col = 1
        self.tokens: List[CSSToken] = []

    def tokenize(self) -> List[CSSToken]:
        """Lex the CSS into tokens."""
        while self.pos < len(self.code):
            ch = self.code[self.pos]

            if ch == '/' and self._peek(1) == '*':
                self._read_comment()
            elif ch in ('"', "'"):
                self._read_string(ch)
            elif ch == '{':
                self.tokens.append(CSSToken(TokenType.OPEN_BRACE, '{', self.line, self.col))
                self._advance()
            elif ch == '}':
                self.tokens.append(CSSToken(TokenType.CLOSE_BRACE, '}', self.line, self.col))
                self._advance()
            elif ch == ';':
                self.tokens.append(CSSToken(TokenType.SEMICOLON, ';', self.line, self.col))
                self._advance()
            elif ch == '@':
                self._read_at_rule()
            elif ch in (' ', '\t', '\r'):
                self._advance()
            elif ch == '\n':
                self._advance()
            else:
                self._read_text()

        return self.tokens

    def _peek(self, offset: int = 0) -> str:
        idx = self.pos + offset
        return self.code[idx] if idx < len(self.code) else ''

    def _advance(self, count: int = 1):
        for _ in range(count):
            if self.pos < len(self.code):
                if self.code[self.pos] == '\n':
                    self.line += 1
                    self.col = 1
                else:
                    self.col += 1
                self.pos += 1

    def _read_comment(self):
        """Read /* ... */ comment."""
        start_line = self.line
        start_col = self.col
        self._advance(2)  # Skip /*
        content = ''
        while self.pos < len(self.code):
            if self.code[self.pos] == '*' and self._peek(1) == '/':
                self._advance(2)
                break
            content += self.code[self.pos]
            self._advance()
        self.tokens.append(CSSToken(TokenType.COMMENT, content, start_line, start_col))

    def _read_string(self, quote: str):
        """Read a quoted string."""
        start_line = self.line
        start_col = self.col
        self._advance()  # Skip opening quote
        content = ''
        while self.pos < len(self.code):
            ch = self.code[self.pos]
            if ch == '\\':
                content += ch
                self._advance()
                if self.pos < len(self.code):
                    content += self.code[self.pos]
                    self._advance()
                continue
            if ch == quote:
                self._advance()
                break
            content += ch
            self._advance()
        self.tokens.append(CSSToken(TokenType.STRING, content, start_line, start_col))

    def _read_at_rule(self):
        """Read @rule (e.g., @media, @keyframes, @apply)."""
        start_line = self.line
        start_col = self.col
        text = ''
        while self.pos < len(self.code) and self.code[self.pos] not in ('{', ';', '\n'):
            text += self.code[self.pos]
            self._advance()
        self.tokens.append(CSSToken(TokenType.AT_RULE, text.strip(), start_line, start_col))

    def _read_text(self):
        """Read selector or property:value text."""
        start_line = self.line
        start_col = self.col
        text = ''
        while self.pos < len(self.code) and self.code[self.pos] not in ('{', '}', ';', '\n'):
            if self.code[self.pos] == '/' and self._peek(1) == '*':
                break
            if self.code[self.pos] in ('"', "'"):
                break
            text += self.code[self.pos]
            self._advance()
        text = text.strip()
        if not text:
            return

        # Classify: if it contains ':', it's a property:value declaration
        if ':' in text and not text.startswith(':'):  # Exclude :root, :hover, etc.
            colon_idx = text.index(':')
            prop = text[:colon_idx].strip()
            val = text[colon_idx + 1:].strip()
            # Check for url() in value
            if 'url(' in val.lower():
                self.tokens.append(CSSToken(TokenType.URL, val, start_line, start_col))
            else:
                self.tokens.append(CSSToken(TokenType.PROPERTY, prop, start_line, start_col))
                self.tokens.append(CSSToken(TokenType.VALUE, val, start_line, start_col))
        else:
            self.tokens.append(CSSToken(TokenType.SELECTOR, text, start_line, start_col))

    def parse_declarations(self) -> List[CSSDeclaration]:
        """Parse tokens into property:value declarations, excluding comments/strings/URLs."""
        if not self.tokens:
            self.tokenize()

        declarations = []
        current_selector = ""
        i = 0
        while i < len(self.tokens):
            tok = self.tokens[i]
            if tok.type == TokenType.SELECTOR:
                current_selector = tok.value
            elif tok.type == TokenType.PROPERTY:
                # Next token should be VALUE
                if i + 1 < len(self.tokens) and self.tokens[i + 1].type == TokenType.VALUE:
                    declarations.append(CSSDeclaration(
                        property=tok.value,
                        value=self.tokens[i + 1].value,
                        line=tok.line,
                        selector=current_selector,
                    ))
                    i += 1  # Skip the value token
            elif tok.type == TokenType.CLOSE_BRACE:
                current_selector = ""
            i += 1

        return declarations

    def parse_rules(self) -> List[CSSRule]:
        """Parse tokens into complete CSS rules."""
        if not self.tokens:
            self.tokenize()

        rules = []
        current_selector = ""
        current_decls = []
        rule_line = 0

        i = 0
        while i < len(self.tokens):
            tok = self.tokens[i]
            if tok.type == TokenType.SELECTOR:
                current_selector = tok.value
                rule_line = tok.line
            elif tok.type == TokenType.PROPERTY:
                if i + 1 < len(self.tokens) and self.tokens[i + 1].type == TokenType.VALUE:
                    current_decls.append(CSSDeclaration(
                        property=tok.value,
                        value=self.tokens[i + 1].value,
                        line=tok.line,
                        selector=current_selector,
                    ))
                    i += 1
            elif tok.type == TokenType.CLOSE_BRACE:
                if current_selector or current_decls:
                    rules.append(CSSRule(
                        selector=current_selector,
                        declarations=current_decls,
                        line=rule_line,
                    ))
                current_selector = ""
                current_decls = []
            i += 1

        return rules

    def get_colors(self) -> List[Tuple[str, int]]:
        """Extract color values from declarations (NOT from comments/strings/URLs)."""
        decls = self.parse_declarations()
        colors = []
        hex_re = re.compile(r'#[0-9a-fA-F]{3,8}\b')
        rgb_re = re.compile(r'rgba?\([^)]+\)')

        for decl in decls:
            for m in hex_re.finditer(decl.value):
                colors.append((m.group(0), decl.line))
            for m in rgb_re.finditer(decl.value):
                colors.append((m.group(0), decl.line))

        return colors

    def get_fonts(self) -> List[Tuple[str, int]]:
        """Extract font-family values from declarations."""
        decls = self.parse_declarations()
        fonts = []
        for decl in decls:
            if 'font-family' in decl.property.lower():
                fonts.append((decl.value, decl.line))
        return fonts

    def get_spacing_values(self) -> List[Tuple[str, str, int]]:
        """Extract spacing values (margin, padding, gap) from declarations.
        Returns (property, value, line)."""
        decls = self.parse_declarations()
        spacing = []
        spacing_props = {'margin', 'padding', 'gap', 'top', 'right', 'bottom', 'left', 'inset',
                         'margin-top', 'margin-right', 'margin-bottom', 'margin-left',
                         'padding-top', 'padding-right', 'padding-bottom', 'padding-left'}
        for decl in decls:
            if decl.property.lower() in spacing_props:
                spacing.append((decl.property, decl.value, decl.line))
        return spacing

    def get_radii(self) -> List[Tuple[str, int]]:
        """Extract border-radius values from declarations."""
        decls = self.parse_declarations()
        radii = []
        for decl in decls:
            if 'border-radius' in decl.property.lower():
                radii.append((decl.value, decl.line))
        return radii
