#!/usr/bin/env python3
"""
Generic Dual-Mode BLE RCSP E-Ink Word Card (YDW012 Series)
Standalone BLE Synchronization Tool, FAT Browser & .CAD/.REV Wordbook Compiler.

Educational & Interoperability Notice:
This tool is an independent, clean-room implementation of a generic BLE GATT/RCSP
communication state machine and binary card container compiler for personal
hardware interoperability and embedded protocol learning. It contains no third-party
proprietary SDKs, firmware code, or copyrighted vocabulary assets.
"""

import argparse
import asyncio
import json
import os
import pathlib
import struct
import sys
import time
from typing import Dict, List, Optional, Tuple

UUID_SERVICE = "0000ae00-0000-1000-8000-00805f9b34fb"
UUID_WRITE = "0000ae01-0000-1000-8000-00805f9b34fb"
UUID_NOTIFY = "0000ae02-0000-1000-8000-00805f9b34fb"
DEFAULT_BLE_PREFIX = os.environ.get("EINK_BLE_PREFIX", "YDW:")

# ============================================================================
# Stage 1: Link-Layer 6-Step Challenge-Response Authentication Cipher
# ============================================================================

KS_TABLE = [
    0x64, 0xAC, 0x28, 0x5A, 0xC9, 0xB3, 0x37, 0xC5, 0x0A, 0x10, 0xB7, 0xA3, 0xBA, 0xB1, 0x97, 0x46,
    0x3D, 0x05, 0xDC, 0x66, 0x6E, 0xF6, 0x9A, 0xF8, 0x0D, 0x58, 0x95, 0x67, 0xC6, 0xAA, 0xAB, 0xEC,
    0xA0, 0x68, 0x9B, 0x96, 0xD4, 0xEB, 0xBF, 0x43, 0x49, 0x36, 0xE9, 0x6A, 0x89, 0xD8, 0xC3, 0x8A,
    0x94, 0x63, 0x99, 0xBC, 0x7B, 0xBE, 0xC1, 0x22, 0xBB, 0x5C, 0x71, 0xD5, 0x1F, 0x92, 0x57, 0x5D,
    0x8F, 0x44, 0x41, 0x1D, 0x51, 0xE6, 0x40, 0x17, 0xFB, 0xFD, 0x19, 0x32, 0x34, 0xB8, 0x61, 0x2A,
    0xCA, 0x23, 0x6F, 0xDA, 0x39, 0xF7, 0xA2, 0x01, 0x7F, 0xD6, 0x31, 0xE7, 0xDE, 0x80, 0x04, 0xDD,
    0x2C, 0x59, 0x82, 0xAF, 0xA8, 0xE0, 0x0F, 0xCD, 0xA1, 0x12, 0x3E, 0x30, 0xD1, 0x1C, 0xD0, 0x3A,
    0x33, 0x72, 0x2E, 0x4F, 0x90, 0x02, 0x13, 0x06, 0x75, 0xCE, 0x87, 0xC2, 0xEF, 0xB2, 0xAD, 0x7D,
    0x38, 0x15, 0xE1, 0x52, 0x9F, 0x7A, 0x6C, 0x2F, 0x27, 0xC4, 0xE2, 0x81, 0xA9, 0xCF, 0x8D, 0xC0,
    0xD7, 0xDF, 0xFF, 0x60, 0x76, 0x14, 0x8C, 0x5E, 0x55, 0x09, 0xE4, 0x08, 0xC7, 0x42, 0x20, 0xFC,
    0xD2, 0x50, 0x91, 0xD9, 0x4C, 0x62, 0x9E, 0xE8, 0xB9, 0xA6, 0xF9, 0x1A, 0x00, 0x21, 0x0B, 0xFA,
    0x35, 0x9C, 0x4E, 0x4B, 0x69, 0x48, 0xCB, 0x0E, 0xC8, 0xA4, 0x5B, 0xEA, 0x84, 0x07, 0xB4, 0x18,
    0xF4, 0xAE, 0x6B, 0xDB, 0xA7, 0xCC, 0x3F, 0x8B, 0x4A, 0x0C, 0x3C, 0x25, 0xE5, 0x54, 0x4D, 0x45,
    0x83, 0xED, 0x11, 0xF0, 0xB0, 0x53, 0x93, 0xF2, 0x74, 0x26, 0xB5, 0x9D, 0x6D, 0x7C, 0xF3, 0x2D,
    0xF1, 0x56, 0x24, 0x7E, 0x47, 0x1B, 0x86, 0xBD, 0x70, 0x8E, 0x1E, 0x3B, 0x73, 0x16, 0x03, 0xB6,
    0xAC, 0x28, 0x5A, 0xC9, 0xB3, 0x37, 0xC5, 0x0A, 0x10, 0xB7, 0xA3, 0xBA, 0xB1, 0x97, 0x46, 0x88,
]

SBOX = [
    0x01, 0x2D, 0xE2, 0x93, 0xBE, 0x45, 0x15, 0xAE, 0x78, 0x03, 0x87, 0xA4, 0xB8, 0x38, 0xCF, 0x3F,
    0x08, 0x67, 0x09, 0x94, 0xEB, 0x26, 0xA8, 0x6B, 0xBD, 0x18, 0x34, 0x1B, 0xBB, 0xBF, 0x72, 0xF7,
    0x40, 0x35, 0x48, 0x9C, 0x51, 0x2F, 0x3B, 0x55, 0xE3, 0xC0, 0x9F, 0xD8, 0xD3, 0xF3, 0x8D, 0xB1,
    0xFF, 0xA7, 0x3E, 0xDC, 0x86, 0x77, 0xD7, 0xA6, 0x11, 0xFB, 0xF4, 0xBA, 0x92, 0x91, 0x64, 0x83,
    0xF1, 0x33, 0xEF, 0xDA, 0x2C, 0xB5, 0xB2, 0x2B, 0x88, 0xD1, 0x99, 0xCB, 0x8C, 0x84, 0x1D, 0x14,
    0x81, 0x97, 0x71, 0xCA, 0x5F, 0xA3, 0x8B, 0x57, 0x3C, 0x82, 0xC4, 0x52, 0x5C, 0x1C, 0xE8, 0xA0,
    0x04, 0xB4, 0x85, 0x4A, 0xF6, 0x13, 0x54, 0xB6, 0xDF, 0x0C, 0x1A, 0x8E, 0xDE, 0xE0, 0x39, 0xFC,
    0x20, 0x9B, 0x24, 0x4E, 0xA9, 0x98, 0x9E, 0xAB, 0xF2, 0x60, 0xD0, 0x6C, 0xEA, 0xFA, 0xC7, 0xD9,
    0x00, 0xD4, 0x1F, 0x6E, 0x43, 0xBC, 0xEC, 0x53, 0x89, 0xFE, 0x7A, 0x5D, 0x49, 0xC9, 0x32, 0xC2,
    0xF9, 0x9A, 0xF8, 0x6D, 0x16, 0xDB, 0x59, 0x96, 0x44, 0xE9, 0xCD, 0xE6, 0x46, 0x42, 0x8F, 0x0A,
    0xC1, 0xCC, 0xB9, 0x65, 0xB0, 0xD2, 0xC6, 0xAC, 0x1E, 0x41, 0x62, 0x29, 0x2E, 0x0E, 0x74, 0x50,
    0x02, 0x5A, 0xC3, 0x25, 0x7B, 0x8A, 0x2A, 0x5B, 0xF0, 0x06, 0x0D, 0x47, 0x6F, 0x70, 0x9D, 0x7E,
    0x10, 0xCE, 0x12, 0x27, 0xD5, 0x4C, 0x4F, 0xD6, 0x79, 0x30, 0x68, 0x36, 0x75, 0x7D, 0xE4, 0xED,
    0x80, 0x6A, 0x90, 0x37, 0xA2, 0x5E, 0x76, 0xAA, 0xC5, 0x7F, 0x3D, 0xAF, 0xA5, 0xE5, 0x19, 0x61,
    0xFD, 0x4D, 0x7C, 0xB7, 0x0B, 0xEE, 0xAD, 0x4B, 0x22, 0xF5, 0xE7, 0x73, 0x23, 0x21, 0xC8, 0x05,
    0xE1, 0x66, 0xDD, 0xB3, 0x58, 0x69, 0x63, 0x56, 0x0F, 0xA1, 0x31, 0x95, 0x17, 0x07, 0x3A, 0x28,
]

ISBOX = [
    0x80, 0x00, 0xB0, 0x09, 0x60, 0xEF, 0xB9, 0xFD, 0x10, 0x12, 0x9F, 0xE4, 0x69, 0xBA, 0xAD, 0xF8,
    0xC0, 0x38, 0xC2, 0x65, 0x4F, 0x06, 0x94, 0xFC, 0x19, 0xDE, 0x6A, 0x1B, 0x5D, 0x4E, 0xA8, 0x82,
    0x70, 0xED, 0xE8, 0xEC, 0x72, 0xB3, 0x15, 0xC3, 0xFF, 0xAB, 0xB6, 0x47, 0x44, 0x01, 0xAC, 0x25,
    0xC9, 0xFA, 0x8E, 0x41, 0x1A, 0x21, 0xCB, 0xD3, 0x0D, 0x6E, 0xFE, 0x26, 0x58, 0xDA, 0x32, 0x0F,
    0x20, 0xA9, 0x9D, 0x84, 0x98, 0x05, 0x9C, 0xBB, 0x22, 0x8C, 0x63, 0xE7, 0xC5, 0xE1, 0x73, 0xC6,
    0xAF, 0x24, 0x5B, 0x87, 0x66, 0x27, 0xF7, 0x57, 0xF4, 0x96, 0xB1, 0xB7, 0x5C, 0x8B, 0xD5, 0x54,
    0x79, 0xDF, 0xAA, 0xF6, 0x3E, 0xA3, 0xF1, 0x11, 0xCA, 0xF5, 0xD1, 0x17, 0x7B, 0x93, 0x83, 0xBC,
    0xBD, 0x52, 0x1E, 0xEB, 0xAE, 0xCC, 0xD6, 0x35, 0x08, 0xC8, 0x8A, 0xB4, 0xE2, 0xCD, 0xBF, 0xD9,
    0xD0, 0x50, 0x59, 0x3F, 0x4D, 0x62, 0x34, 0x0A, 0x48, 0x88, 0xB5, 0x56, 0x4C, 0x2E, 0x6B, 0x9E,
    0xD2, 0x3D, 0x3C, 0x03, 0x13, 0xFB, 0x97, 0x51, 0x75, 0x4A, 0x91, 0x71, 0x23, 0xBE, 0x76, 0x2A,
    0x5F, 0xF9, 0xD4, 0x55, 0x0B, 0xDC, 0x37, 0x31, 0x16, 0x74, 0xD7, 0x77, 0xA7, 0xE6, 0x07, 0xDB,
    0xA4, 0x2F, 0x46, 0xF3, 0x61, 0x45, 0x67, 0xE3, 0x0C, 0xA2, 0x3B, 0x1C, 0x85, 0x18, 0x04, 0x1D,
    0x29, 0xA0, 0x8F, 0xB2, 0x5A, 0xD8, 0xA6, 0x7E, 0xEE, 0x8D, 0x53, 0x4B, 0xA1, 0x9A, 0xC1, 0x0E,
    0x7A, 0x49, 0xA5, 0x2C, 0x81, 0xC4, 0xC7, 0x36, 0x2B, 0x7F, 0x43, 0x95, 0x33, 0xF2, 0x6C, 0x68,
    0x6D, 0xF0, 0x02, 0x28, 0xCE, 0xDD, 0x9B, 0xEA, 0x5E, 0x99, 0x7C, 0x14, 0x86, 0xCF, 0xE5, 0x42,
    0xB8, 0x40, 0x78, 0x2D, 0x3A, 0xE9, 0x64, 0x1F, 0x92, 0x90, 0x7D, 0x39, 0x6F, 0xE0, 0x89, 0x30,
]

STATIC_KEY = [
    0x06, 0x77, 0x5F, 0x87, 0x91, 0x8D, 0xD4, 0x23,
    0x00, 0x5D, 0xF1, 0xD8, 0xCF, 0x0C, 0x14, 0x2B,
]

MAGIC = [0x11, 0x22, 0x33, 0x33, 0x22, 0x11]
MASK = 0x9999


def _key_schedule(data16: List[int]) -> List[int]:
    out = [0] * 272
    for i in range(16):
        out[i] = data16[i]
    buf = list(data16[:16])
    checksum = 0
    for b in data16:
        checksum ^= b
    buf.append(checksum & 0xFF)
    for rnd in range(16):
        for i in range(17):
            b = buf[i]
            buf[i] = ((b << 3) | (b >> 5)) & 0xFF
        read_pos = (rnd + 1) % 17
        for j in range(16):
            src = buf[read_pos]
            tbl_idx = 0xF + rnd * 16 - j
            out[16 + rnd * 16 + j] = (KS_TABLE[tbl_idx] + src) & 0xFF
            read_pos += 1
            if read_pos > 16:
                read_pos = 0
    return out


def _pair_mix(s: List[int]) -> List[int]:
    out = list(s)
    for i in range(0, 16, 2):
        b0, b1 = out[i], out[i + 1]
        out[i] = (b1 + (b0 << 1)) & 0xFF
        out[i + 1] = (b1 + b0) & 0xFF
    return out


def _permute_16(s: List[int]) -> List[int]:
    idx = [8, 11, 12, 15, 2, 1, 6, 5, 10, 9, 14, 13, 0, 7, 4, 3]
    return [s[i] for i in idx]


def _fibonacci_mix(s: List[int]) -> List[int]:
    s = _pair_mix(s)
    s = _permute_16(s)
    s = _pair_mix(s)
    s = _permute_16(s)
    s = _pair_mix(s)
    s = _permute_16(s)
    s = _pair_mix(s)
    return s


def _cond_mix(state: List[int], key_block: List[int], mask: int, phase: int) -> List[int]:
    res = list(state)
    for i in range(16):
        bit_set = ((1 << i) & mask) != 0
        if phase == 3:
            res[i] = (res[i] ^ key_block[i]) if bit_set else ((key_block[i] + res[i]) & 0xFF)
        else:
            res[i] = ((key_block[i] + res[i]) & 0xFF) if bit_set else (res[i] ^ key_block[i])
    return res


def _sbox_sub(state: List[int]) -> List[int]:
    res = list(state)
    for pos in [0, 3, 4, 7, 8, 11, 12, 15]:
        res[pos] = SBOX[res[pos]]
    for pos in [1, 2, 5, 6, 9, 10, 13, 14]:
        res[pos] = ISBOX[res[pos]]
    return res


def _block_cipher(state_in: List[int], ek: List[int], mode: int) -> List[int]:
    s = list(state_in)
    initial = list(state_in)
    for r5 in range(8):
        if mode != 0 and r5 == 2:
            for i in range(16):
                bit_set = ((1 << i) & MASK) != 0
                s[i] = (s[i] ^ initial[i]) if bit_set else ((initial[i] + s[i]) & 0xFF)
        ek_off = r5 * 0x20
        s = _cond_mix(s, ek[ek_off : ek_off + 16], MASK, 3)
        s = _sbox_sub(s)
        s = _cond_mix(s, ek[ek_off + 16 : ek_off + 32], MASK, 5)
        s = _fibonacci_mix(s)
    s = _cond_mix(s, ek[0x100:0x110], MASK, 3)
    return s


def function_e1test(key6: List[int], input16: List[int], seed16: List[int]) -> List[int]:
    expanded_key = [key6[i % 6] for i in range(16)]
    ks1 = _key_schedule(seed16[:16])
    cipher_out = _block_cipher(input16[:16], ks1, 0)
    for i in range(16):
        cipher_out[i] = (expanded_key[i] + (cipher_out[i] ^ input16[i])) & 0xFF
    obf = [
        (seed16[0] - 0x17) & 0xFF,
        (seed16[1] ^ 0xE5),
        (seed16[2] - 0x21) & 0xFF,
        (seed16[3] ^ 0xC1),
        (seed16[4] - 0x4D) & 0xFF,
        (seed16[5] ^ 0xA7),
        (seed16[6] - 0x6B) & 0xFF,
        (seed16[7] ^ 0x83),
        (seed16[8] ^ 0xE9),
        (seed16[9] - 0x1B) & 0xFF,
        (seed16[10] ^ 0xDF),
        (seed16[11] - 0x3F) & 0xFF,
        (seed16[12] ^ 0xB3),
        (seed16[13] - 0x59) & 0xFF,
        (seed16[14] ^ 0x95),
        (seed16[15] - 0x7D) & 0xFF,
    ]
    ks2 = _key_schedule(obf)
    return _block_cipher(cipher_out, ks2, 1)


def get_encrypted_auth_data(data17: bytes) -> bytes:
    """Compute the 17-byte JL_AUTH response (0x01 + 16 encrypted bytes) for a 17-byte challenge."""
    if len(data17) != 17:
        raise ValueError(f"Expected 17-byte challenge, got {len(data17)} bytes")
    enc = function_e1test(MAGIC, list(data17[1:17]), STATIC_KEY)
    return bytes([0x01] + enc)


def crc16_xmodem(data: bytes, crc: int = 0) -> int:
    """Standard CRC-16/XMODEM (poly=0x1021, init=0x0000) used by RCSP framing."""
    for b in data:
        crc ^= (b & 0xFF) << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc & 0xFFFF


# ============================================================================
# 2. Bit-Accurate .CAD & .REV Binary Compiler and Parser
# ============================================================================


def build_cad(
    entries: List[Dict[str, str]],
    book_id: int,
    title: str,
    ts_ms: int = 1681960781000,
    lang: int = 13,
    cat: int = 3,
) -> bytes:
    """
    Compile a list of {"headword": ..., "definition": ...} dicts into a bit-accurate
    YDW012 .CAD wordbook binary.
    """
    N = len(entries)
    sec1_off = 0x84
    sec1_rec_start = sec1_off + 8 + 4 * N
    sec1_str_start = sec1_rec_start + 59 * N

    sec1_ptrs = []
    sec1_recs = []
    sec1_strs = bytearray()
    cur_off = sec1_str_start
    for i, e in enumerate(entries):
        sec1_ptrs.append(struct.pack("<I", sec1_rec_start + i * 59))
        wb = e["headword"].encode("utf-8")
        w_len = len(wb)
        w_off = cur_off
        end_off = w_off + w_len
        cur_off = end_off
        sec1_strs.extend(wb)
        rec = (
            struct.pack("<II", w_len, w_off)
            + struct.pack("<II", 0, end_off)
            + struct.pack("<HI", 0, end_off)
            + struct.pack("<II", 0, end_off) * 4
            + b"\x00" * 5
        )
        assert len(rec) == 59
        sec1_recs.append(rec)

    meta_off = cur_off
    title_bytes = title.encode("utf-8")
    t_len = len(title_bytes)
    title_off = meta_off + 44
    meta_block = struct.pack("<IQQIIIIQ", 1, book_id, ts_ms, 0, lang, cat, t_len, title_off) + title_bytes

    sec2_off = meta_off + len(meta_block)
    sec2_rec_start = sec2_off + 8 + 4 * N
    sec2_str_start = sec2_rec_start + 37 * N

    sec2_ptrs = []
    sec2_recs = []
    sec2_strs = bytearray()
    cur2_off = sec2_str_start
    for i, e in enumerate(entries):
        sec2_ptrs.append(struct.pack("<I", sec2_rec_start + i * 37))
        db = e["definition"].encode("utf-8")
        d_len = len(db)
        d_off = cur2_off
        end_off = d_off + d_len
        cur2_off = end_off
        sec2_strs.extend(db)
        rec = (
            struct.pack("<II", d_len, d_off)
            + struct.pack("<II", 0, end_off) * 3
            + b"\x00" * 5
        )
        assert len(rec) == 37
        sec2_recs.append(rec)

    header = struct.pack("<6I", 0, 0, sec1_off, meta_off, sec2_off, 0) + b"\x00" * (sec1_off - 24)
    sec1 = struct.pack("<II", N, 0) + b"".join(sec1_ptrs) + b"".join(sec1_recs) + bytes(sec1_strs)
    sec2 = struct.pack("<II", N, 0) + b"".join(sec2_ptrs) + b"".join(sec2_recs) + bytes(sec2_strs)
    return header + sec1 + meta_block + sec2


def parse_cad(data: bytes) -> Dict:
    """Parse a YDW012 .CAD binary back into metadata and entries."""
    _, _, sec1_off, meta_off, sec2_off, _ = struct.unpack("<6I", data[:24])
    n1, _ = struct.unpack("<II", data[sec1_off : sec1_off + 8])
    n2, _ = struct.unpack("<II", data[sec2_off : sec2_off + 8])
    if n1 != n2:
        raise ValueError(f"Section count mismatch: sec1={n1} vs sec2={n2}")

    ver, book_id, ts_ms, _, lang, cat, t_len, title_off = struct.unpack("<IQQIIIIQ", data[meta_off : meta_off + 44])
    title = data[title_off : title_off + t_len].decode("utf-8")

    entries = []
    for i in range(n1):
        p1 = struct.unpack("<I", data[sec1_off + 8 + 4 * i : sec1_off + 12 + 4 * i])[0]
        w_len, w_off = struct.unpack("<II", data[p1 : p1 + 8])
        headword = data[w_off : w_off + w_len].decode("utf-8")

        p2 = struct.unpack("<I", data[sec2_off + 8 + 4 * i : sec2_off + 12 + 4 * i])[0]
        d_len, d_off = struct.unpack("<II", data[p2 : p2 + 8])
        definition = data[d_off : d_off + d_len].decode("utf-8")

        entries.append({"headword": headword, "definition": definition})

    return {
        "version": ver,
        "book_id": book_id,
        "timestamp_ms": ts_ms,
        "lang": lang,
        "category": cat,
        "title": title,
        "words_count": n1,
        "entries": entries,
    }


def build_rev(
    entries: List[Dict[str, str]],
    book_id: int,
    daily_words: int = 15,
    ts1_ms: int = 1681960781000,
    ts2_ms: int = 1743309352000,
) -> bytes:
    """
    Compile a list of {"headword": ...} dicts into a bit-accurate YDW012 .REV
    Ebbinghaus spaced-repetition schedule file.
    """
    N = len(entries)
    sec1_off = 0x38
    sec1_str_start = sec1_off + 6 * N
    sec1_idx = []
    sec1_strs = bytearray()
    cur_off = sec1_str_start
    for e in entries:
        wb = e["headword"].encode("utf-8")
        w_len = len(wb)
        sec1_idx.append(struct.pack("<HI", w_len, cur_off))
        sec1_strs.extend(wb)
        cur_off += w_len

    sec2_off = cur_off
    G = (N + daily_words - 1) // daily_words
    K = G + 40
    d_str_start = sec2_off + 4 + 6 * K
    sec2_idx = []
    sec2_strs = bytearray()
    cur2_off = d_str_start
    for d in range(K):
        if d == 0:
            s_bytes = b""
        else:
            active_groups = [d - off for off in (0, 2, 6, 14, 29, 39) if 1 <= d - off <= G]
            word_indices = []
            for g in active_groups:
                start_idx = (g - 1) * daily_words + 1
                end_idx = min(g * daily_words, N)
                word_indices.extend(range(start_idx, end_idx + 1))
            s_bytes = ",".join(str(idx) for idx in word_indices).encode("ascii")
        sec2_idx.append(struct.pack("<HI", len(s_bytes), cur2_off))
        sec2_strs.extend(s_bytes)
        cur2_off += len(s_bytes)

    header = struct.pack("<QQQQQIIII", 1, book_id, ts1_ms, ts2_ms, daily_words, N, sec1_off, sec2_off, 0)
    sec1 = b"".join(sec1_idx) + bytes(sec1_strs)
    sec2 = struct.pack("<I", K) + b"".join(sec2_idx) + bytes(sec2_strs)
    return header + sec1 + sec2


def parse_rev(data: bytes) -> Dict:
    """Parse a YDW012 .REV binary back into header metadata, headwords, and daily schedules."""
    ver, book_id, ts1_ms, ts2_ms, daily_words, N, sec1_off, sec2_off, _ = struct.unpack("<QQQQQIIII", data[:56])
    headwords = []
    for i in range(N):
        idx_off = sec1_off + 6 * i
        w_len, w_off = struct.unpack("<HI", data[idx_off : idx_off + 6])
        headwords.append(data[w_off : w_off + w_len].decode("utf-8"))

    K = struct.unpack("<I", data[sec2_off : sec2_off + 4])[0]
    days = []
    for d in range(K):
        idx_off = sec2_off + 4 + 6 * d
        s_len, s_off = struct.unpack("<HI", data[idx_off : idx_off + 6])
        days.append(data[s_off : s_off + s_len].decode("ascii"))

    return {
        "version": ver,
        "book_id": book_id,
        "ts1_ms": ts1_ms,
        "ts2_ms": ts2_ms,
        "daily_words": daily_words,
        "words_count": N,
        "headwords": headwords,
        "days": days,
    }


def format_bilingual_entries(json_path: str) -> List[Dict[str, str]]:
    """
    Convert a JSON word list into {"headword", "definition"} pairs formatted
    for YDW012's E-Ink display. Supports both {"headword", "definition"} and
    {"word", "zh", "category_zh", "category", "translation"} schemas.
    """
    with open(json_path, "r", encoding="utf-8") as f:
        items = json.load(f)
    entries = []
    for item in items:
        if "headword" in item and "definition" in item:
            entries.append({"headword": str(item["headword"]).strip(), "definition": str(item["definition"])})
            continue
        word = item["word"].strip()
        zh = item.get("zh", "").strip()
        cat_zh = item.get("category_zh", "").strip()
        cat_en = item.get("category", "").strip()
        trans = item["translation"].strip()
        header_line = f"{zh} [{cat_zh}/{cat_en}]" if (zh and cat_zh) else (zh or f"[{cat_en}]")
        t_formatted = (
            trans.replace(" EN: ", "\n\nEN: ")
            .replace(" 公式: ", "\n\n公式: ")
            .replace(" 例: ", "\n\n例: ")
        )
        definition = f"{header_line}\n\n{t_formatted}\n"
        entries.append({"headword": word, "definition": definition})
    return entries


# ============================================================================
# Stage 3: Standard RCSP & Custom 0xFF Extension Protocol Framing
# ============================================================================


def pack_rcsp_cmd(
    opcode: int,
    param: bytes = b"",
    sn: int = 0,
    has_resp: bool = True,
    xm_opcode: Optional[int] = None,
) -> bytes:
    flags = 0x80 | (0x40 if has_resp else 0x00)
    if opcode == 0x01 and xm_opcode is not None:
        body = bytes([sn & 0xFF, xm_opcode & 0xFF]) + param
    else:
        body = bytes([sn & 0xFF]) + param
    return b"\xFE\xDC\xBA" + struct.pack(">BBH", flags, opcode, len(body)) + body + b"\xEF"


def pack_rcsp_resp(
    opcode: int,
    status: int = 0,
    sn: int = 0,
    param: bytes = b"",
    xm_opcode: Optional[int] = None,
) -> bytes:
    flags = 0x00
    if opcode == 0x01 and xm_opcode is not None:
        body = bytes([status & 0xFF, sn & 0xFF, xm_opcode & 0xFF]) + param
    else:
        body = bytes([status & 0xFF, sn & 0xFF]) + param
    return b"\xFE\xDC\xBA" + struct.pack(">BBH", flags, opcode, len(body)) + body + b"\xEF"


def pack_SetWordBookMsg(books: List[Dict], curr_book_id: int, curr_book_type: int = 1) -> bytes:
    out = bytearray(struct.pack("<HH", 0x0075, len(books)))
    for b in books:
        rec = struct.pack(
            "<QQIBHHBHBBB",
            b["book_id"],
            b.get("book_version", 1681960781000),
            b.get("task_id", b["book_id"]),
            b.get("book_type", 1),
            b["words_count"],
            b.get("curr_index", 0),
            b.get("learn_mode", 1),
            b.get("per_time_size", 15),
            b.get("sound_count", 1),
            b.get("voice_type", 2),
            b.get("display_content", 0),
        )
        assert len(rec) == 31
        out.extend(rec)
    out.extend(struct.pack("<QB", curr_book_id, curr_book_type))
    return bytes(out)


def pack_TransportBookMsg(book_id: int, book_type: int = 1, file_mask: int = 3) -> bytes:
    return struct.pack("<HQBB", 0x007A, book_id, book_type, file_mask)


def parse_file_browse_entries(data: bytes) -> List[Dict]:
    """Parse RCSP FileBrowse (0x01 / xm_opcode=0x0C) directory listing payload."""
    entries = []
    pos = 0
    while pos + 7 < len(data):
        flags = data[pos]
        is_file = bool(flags & 0x01)
        is_ansi = bool(flags & 0x02)
        dev_idx = (flags & 0x1C) >> 2
        cluster = struct.unpack(">I", data[pos + 1 : pos + 5])[0]
        file_num = struct.unpack(">H", data[pos + 5 : pos + 7])[0]
        name_len = data[pos + 7]
        pos += 8
        name_bytes = data[pos : pos + name_len]
        pos += name_len
        name = name_bytes.decode("gbk" if is_ansi else "utf-16le", errors="replace")
        entries.append(
            {
                "name": name,
                "is_file": is_file,
                "is_ansi": is_ansi,
                "dev_index": dev_idx,
                "cluster": cluster,
                "file_num": file_num,
            }
        )
    return entries


# ============================================================================
# 4. YDW012 BLE Session & Operations
# ============================================================================


class YDW012Session:
    def __init__(self, client):
        self.client = client
        self.sn = 1
        self.authed = False
        self.rx_raw_queue = asyncio.Queue()
        self.rx_buf = bytearray()
        self.pkt_queue = asyncio.Queue()
        self.ble_mtu = 240

    def next_sn(self) -> int:
        s = self.sn
        self.sn = (self.sn + 1) & 0xFF
        return s

    def on_notify(self, sender, data: bytearray):
        b = bytes(data)
        if not self.authed:
            self.rx_raw_queue.put_nowait(b)
            return
        self.rx_buf.extend(b)
        while True:
            idx = self.rx_buf.find(b"\xFE\xDC\xBA")
            if idx == -1:
                if len(self.rx_buf) > 2:
                    del self.rx_buf[:-2]
                break
            if idx > 0:
                del self.rx_buf[:idx]
            if len(self.rx_buf) < 8:
                break
            flags, opcode, plen = struct.unpack(">BBH", self.rx_buf[3:7])
            if plen > 1024:
                del self.rx_buf[:3]
                continue
            total_len = 7 + plen + 1
            if len(self.rx_buf) < total_len:
                break
            raw = bytes(self.rx_buf[:total_len])
            del self.rx_buf[:total_len]
            if raw[-1] != 0xEF:
                continue
            body = raw[7:-1]
            is_cmd = bool(flags & 0x80)
            has_resp = bool(flags & 0x40)
            if is_cmd:
                sn = body[0] if len(body) >= 1 else 0
                if opcode == 0x01 and len(body) >= 2:
                    xm_op = body[1]
                    payload = body[2:]
                else:
                    xm_op = None
                    payload = body[1:]
                status = None
            else:
                status = body[0] if len(body) >= 1 else 0
                sn = body[1] if len(body) >= 2 else 0
                if opcode == 0x01 and len(body) >= 3:
                    xm_op = body[2]
                    payload = body[3:]
                else:
                    xm_op = None
                    payload = body[2:]
            self.pkt_queue.put_nowait(
                {
                    "is_cmd": is_cmd,
                    "has_resp": has_resp,
                    "opcode": opcode,
                    "xm_op": xm_op,
                    "status": status,
                    "sn": sn,
                    "payload": payload,
                    "raw": raw,
                }
            )

    async def authenticate_and_init(self):
        try:
            await self.client._backend._acquire_mtu()
        except Exception:
            pass
        if self.client.mtu_size and self.client.mtu_size > 23:
            self.ble_mtu = min(509, self.client.mtu_size - 3)
        print(f"Connected! BLE MTU={self.client.mtu_size} (write chunk={self.ble_mtu})", flush=True)
        await self.client.start_notify(UUID_NOTIFY, self.on_notify)
        await asyncio.sleep(0.2)

        # 6-step JL_AUTH handshake on raw 0xAE01 / 0xAE02
        rand17 = b"\x00" + os.urandom(16)
        expected_dev = get_encrypted_auth_data(rand17)
        await self.client.write_gatt_char(UUID_WRITE, rand17, response=False)
        while True:
            msg = await asyncio.wait_for(self.rx_raw_queue.get(), timeout=5.0)
            if len(msg) == 17 and msg[0] == 0x01:
                if msg != expected_dev:
                    raise RuntimeError("JL_AUTH challenge-response mismatch!")
                await self.client.write_gatt_char(UUID_WRITE, b"\x02pass", response=False)
            elif len(msg) == 17 and msg[0] == 0x00:
                await self.client.write_gatt_char(UUID_WRITE, get_encrypted_auth_data(msg), response=False)
            elif msg == b"\x02pass":
                self.authed = True
                print("=== JL_AUTH Handshake Complete ===", flush=True)
                break
        await asyncio.sleep(0.2)
        # Mandatory first RCSP command: GetTargetInfoCmd (0x03)
        resp03 = await self.send_cmd_wait_resp(0x03, struct.pack(">IB", 0xFFFFFFFF, 0), timeout=5.0)
        print(
            f"=== RCSP GetTargetInfoCmd (0x03) status={resp03['status']} len={len(resp03['payload'])} ===",
            flush=True,
        )

    async def write_raw(self, data: bytes):
        for i in range(0, len(data), self.ble_mtu):
            chunk = data[i : i + self.ble_mtu]
            await self.client.write_gatt_char(UUID_WRITE, chunk, response=False)
            if i + self.ble_mtu < len(data):
                await asyncio.sleep(0.01)

    async def send_cmd_wait_resp(self, opcode: int, param: bytes = b"", timeout: float = 5.0) -> Dict:
        sn = self.next_sn()
        pkt = pack_rcsp_cmd(opcode, param, sn=sn, has_resp=True)
        await self.write_raw(pkt)
        deadline = time.monotonic() + timeout
        while True:
            rem = deadline - time.monotonic()
            if rem <= 0:
                raise TimeoutError(f"Timeout waiting for response to OpCode 0x{opcode:02X}")
            rx = await asyncio.wait_for(self.pkt_queue.get(), timeout=rem)
            if not rx["is_cmd"] and rx["opcode"] == opcode:
                return rx
            if rx["is_cmd"] and rx["opcode"] == 0xFF and rx["has_resp"]:
                ack = pack_rcsp_resp(0xFF, status=0, sn=rx["sn"], param=b"\x00")
                await self.write_raw(ack)

    async def send_ext_msg(
        self, yd_payload: bytes, expect_msg_type: Optional[int] = None, timeout: float = 5.0
    ) -> Tuple[Optional[Dict], Optional[Dict]]:
        sn = self.next_sn()
        pkt = pack_rcsp_cmd(0xFF, yd_payload, sn=sn, has_resp=True)
        await self.write_raw(pkt)
        deadline = time.monotonic() + timeout
        got_rcsp_resp = None
        got_yd_cmd = None
        while True:
            rem = deadline - time.monotonic()
            if rem <= 0:
                break
            try:
                rx = await asyncio.wait_for(self.pkt_queue.get(), timeout=rem)
            except asyncio.TimeoutError:
                break
            if not rx["is_cmd"] and rx["opcode"] == 0xFF:
                got_rcsp_resp = rx
                if expect_msg_type is None:
                    return got_rcsp_resp, got_yd_cmd
            elif rx["is_cmd"] and rx["opcode"] == 0xFF:
                if rx["has_resp"]:
                    ack = pack_rcsp_resp(0xFF, status=0, sn=rx["sn"], param=b"\x00")
                    await self.write_raw(ack)
                if len(rx["payload"]) >= 2:
                    mtype = struct.unpack("<H", rx["payload"][:2])[0]
                    if expect_msg_type is None or mtype == expect_msg_type:
                        got_yd_cmd = rx
                        return got_rcsp_resp, got_yd_cmd
        return got_rcsp_resp, got_yd_cmd

    async def browse_dir(self, path_clusters: List[int] = None, dev_handler: int = 1) -> List[Dict]:
        """List files/folders in a directory specified by its chain of FAT cluster numbers (root=[0])."""
        if path_clusters is None:
            path_clusters = [0]
        all_entries = []
        start_idx = 1
        read_num = 10
        while True:
            path_bytes = b"".join(struct.pack(">I", c) for c in path_clusters)
            param = struct.pack(">BBHIH", 0, read_num, start_idx, dev_handler, len(path_bytes)) + path_bytes
            sn = self.next_sn()
            await self.write_raw(pack_rcsp_cmd(0x0C, param, sn=sn, has_resp=True))
            batch = []
            stopped = False
            reason = 0
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                rx = await asyncio.wait_for(self.pkt_queue.get(), timeout=max(0.1, deadline - time.monotonic()))
                if not rx["is_cmd"] and rx["opcode"] == 0x0C:
                    if rx["status"] != 0:
                        return all_entries
                elif rx["is_cmd"] and rx["opcode"] == 0x01 and rx["xm_op"] == 0x0C:
                    batch.extend(parse_file_browse_entries(rx["payload"]))
                elif rx["is_cmd"] and rx["opcode"] == 0x0D:
                    reason = rx["payload"][0] if rx["payload"] else 0
                    await self.write_raw(pack_rcsp_resp(0x0D, status=0, sn=rx["sn"], param=b"\x00"))
                    stopped = True
                    break
            all_entries.extend(batch)
            if not batch or len(batch) < read_num or (stopped and reason == 1):
                break
            start_idx += len(batch)
        return all_entries

    async def pull_file_by_cluster(self, cluster: int, dev_handler: int = 1) -> bytes:
        """Download a file from the device FAT filesystem by its cluster ID via ReadFileFromDeviceCmd (0x24)."""
        param = struct.pack(">BIII", 1, dev_handler, 0, cluster)
        sn = self.next_sn()
        await self.write_raw(pack_rcsp_cmd(0x24, param, sn=sn, has_resp=True))
        file_size = None
        buf = bytearray()
        running_crc = 0
        while True:
            rx = await asyncio.wait_for(self.pkt_queue.get(), timeout=10.0)
            op = rx["opcode"]
            if not rx["is_cmd"] and op == 0x24:
                if rx["status"] != 0:
                    raise RuntimeError(f"ReadFileFromDeviceCmd (0x24) failed: status={rx['status']}")
                if len(rx["payload"]) >= 4:
                    file_size = struct.unpack(">I", rx["payload"][:4])[0]
                    print(f"  [Pull] File size = {file_size} bytes", flush=True)
            elif rx["is_cmd"] and op == 0x01 and rx["xm_op"] == 0x24:
                pl = rx["payload"]
                offset = struct.unpack(">I", pl[0:4])[0]
                pkt_crc = struct.unpack(">H", pl[4:6])[0]
                chunk = pl[6:]
                if offset != len(buf):
                    raise RuntimeError(f"Offset mismatch during pull: expected {len(buf)}, got {offset}")
                running_crc = crc16_xmodem(chunk, running_crc)
                if running_crc != pkt_crc:
                    raise RuntimeError(f"CRC mismatch at offset {offset}: expected 0x{pkt_crc:04X}, got 0x{running_crc:04X}")
                buf.extend(chunk)
            elif rx["is_cmd"] and op == 0x24:
                sub_op = rx["payload"][0] if rx["payload"] else 0x80
                await self.write_raw(pack_rcsp_resp(0x24, status=0, sn=rx["sn"], param=bytes([sub_op])))
                break
        return bytes(buf)

    async def upload_file(self, filename: str, file_bytes: bytes, dev_handler: int = 1) -> bool:
        """Upload a file (.cad or .rev) to YDW012 via RCSP LargeFileTransfer (0x21 -> 0x27 -> 0x1B -> 0x20 -> 0x1D -> 0x1C)."""
        print(f"  [TransferTask] Preparing env for {filename} ({len(file_bytes)} bytes)...", flush=True)
        resp21 = await self.send_cmd_wait_resp(0x21, b"\x00", timeout=5.0)
        print(f"  [TransferTask] NotifyPrepareEnv (0x21) status={resp21['status']}", flush=True)

        use_pkg_crc16 = False
        ext_param = struct.pack(">BIB", 0, dev_handler, 0)
        resp27 = await self.send_cmd_wait_resp(0x27, ext_param, timeout=3.0)
        print(
            f"  [TransferTask] DeviceExtendParam (0x27) status={resp27['status']} payload={resp27['payload'].hex()}",
            flush=True,
        )
        if resp27["status"] == 0 and len(resp27["payload"]) >= 2:
            use_pkg_crc16 = bool(resp27["payload"][1])

        file_crc = crc16_xmodem(file_bytes)
        hash_bytes = f"{file_crc:04x}{len(file_bytes)&0xFFFF:04x}.tmp\x00".encode("ascii")
        assert len(hash_bytes) == 13
        start_param = struct.pack(">IH", len(file_bytes), file_crc) + hash_bytes
        print(
            f"  [TransferTask] Starting LargeFileTransfer (0x1B): size={len(file_bytes)}, crc16=0x{file_crc:04X}...",
            flush=True,
        )
        sn1b = self.next_sn()
        await self.write_raw(pack_rcsp_cmd(0x1B, start_param, sn=sn1b, has_resp=True))

        transfer_mtu = 265
        t_start = time.monotonic()
        while True:
            rx = await asyncio.wait_for(self.pkt_queue.get(), timeout=15.0)
            op = rx["opcode"]
            if not rx["is_cmd"] and op == 0x1B:
                if rx["status"] != 0:
                    raise RuntimeError(
                        f"StartLargeFileTransfer (0x1B) failed with status={rx['status']} payload={rx['payload'].hex()}"
                    )
                if len(rx["payload"]) >= 2:
                    m = struct.unpack(">H", rx["payload"][:2])[0]
                    if m > 0:
                        transfer_mtu = m
                print(f"  [TransferTask] 0x1B accepted! transfer_mtu={transfer_mtu}", flush=True)

            elif rx["is_cmd"] and op == 0x20:
                name_bytes = filename.encode("gbk") + b"\x00\x00"
                resp20 = pack_rcsp_resp(0x20, status=0, sn=rx["sn"], param=name_bytes)
                await self.write_raw(resp20)
                print(f"  [TransferTask] Sent filename response (0x20): {filename!r} ({name_bytes.hex()})", flush=True)

            elif rx["is_cmd"] and op == 0x1D:
                pl = rx["payload"]
                op_flag = pl[0]
                buf_size = struct.unpack(">H", pl[1:3])[0]
                offset = struct.unpack(">I", pl[3:7])[0]
                pct = min(100.0, (offset + buf_size) * 100.0 / max(1, len(file_bytes)))
                print(
                    f"  [TransferTask] 0x1D request: op={op_flag} offset={offset}/{len(file_bytes)} buf_size={buf_size} ({pct:.1f}%)",
                    flush=True,
                )
                if op_flag == 0:
                    window = file_bytes[offset : min(offset + buf_size, len(file_bytes))]
                    seq = 0
                    for i in range(0, len(window), transfer_mtu):
                        chunk = window[i : i + transfer_mtu]
                        if use_pkg_crc16:
                            c_crc = crc16_xmodem(chunk)
                            data_param = bytes([seq & 0xFF, (c_crc >> 8) & 0xFF, c_crc & 0xFF]) + chunk
                        else:
                            data_param = bytes([seq & 0xFF]) + chunk
                        data_pkt = pack_rcsp_cmd(
                            0x01,
                            data_param,
                            sn=self.next_sn(),
                            has_resp=False,
                            xm_opcode=0x1D,
                        )
                        await self.write_raw(data_pkt)
                        seq += 1
                        await asyncio.sleep(0.015)

            elif rx["is_cmd"] and op == 0x1C:
                reason = rx["payload"][0] if rx["payload"] else 0
                resp1c = pack_rcsp_resp(0x1C, status=0, sn=rx["sn"], param=bytes([reason]))
                await self.write_raw(resp1c)
                elapsed = time.monotonic() - t_start
                print(
                    f"  [TransferTask] StopLargeFileTransfer (0x1C): reason={reason} ({'SUCCESS' if reason == 0 else 'ERROR'}) in {elapsed:.1f}s",
                    flush=True,
                )
                if reason != 0:
                    raise RuntimeError(f"StopLargeFileTransfer returned non-zero reason={reason}")
                return True

            elif rx["is_cmd"] and op == 0xFF:
                if rx["has_resp"]:
                    ack = pack_rcsp_resp(0xFF, status=0, sn=rx["sn"], param=b"\x00")
                    await self.write_raw(ack)
                if len(rx["payload"]) >= 2:
                    mtype = struct.unpack("<H", rx["payload"][:2])[0]
                    print(f"  [TransferTask] Async Ext 0xFF msgType=0x{mtype:04X}: {rx['payload'].hex()}", flush=True)


async def resolve_device(addr: Optional[str] = None, timeout: float = 10.0):
    from bleak import BleakScanner

    if addr and addr.lower() != "auto":
        print(f"Looking for YDW012 at {addr}...", flush=True)
        dev = await BleakScanner.find_device_by_address(addr, timeout=timeout)
        return dev or addr

    print("Scanning for nearby YDW012 word cards (BLE prefix 'YDW:')...", flush=True)
    devices = await BleakScanner.discover(timeout=timeout, return_adv=True)
    for d, adv in devices.values():
        name = d.name or adv.local_name or ""
        uuids = [u.lower() for u in (adv.service_uuids or [])]
        if name.startswith("YDW:") or UUID_SERVICE in uuids:
            print(f"Found YDW012: {d.address} ({name})", flush=True)
            return d
    raise RuntimeError("No YDW012 word card found nearby. Wake the card screen and ensure Bluetooth is enabled.")


async def query_device_books(sess: YDW012Session) -> List[Dict]:
    print("\n--- Querying YDW012 Device Status & Books ---", flush=True)
    existing_books = []
    _, yd_task = await sess.send_ext_msg(b"\x03\x00", expect_msg_type=0x0004, timeout=4.0)
    if yd_task:
        pl = yd_task["payload"]
        _, count = struct.unpack("<HH", pl[:4])
        books = [struct.unpack("<Q", pl[4 + i * 8 : 12 + i * 8])[0] for i in range(count)]
        print(f"GetTaskWordBookResultMsg (0x0004): count={count}, bookIds={books}", flush=True)
        for bid in books:
            req = struct.pack("<HQB", 0x0077, bid, 1)
            _, yd_info = await sess.send_ext_msg(req, expect_msg_type=0x0078, timeout=4.0)
            if yd_info and len(yd_info["payload"]) >= 34:
                ipl = yd_info["payload"]
                (
                    _,
                    r_bid,
                    r_ver,
                    r_tid,
                    r_btype,
                    r_wcnt,
                    r_cidx,
                    r_lmode,
                    r_psize,
                    r_scnt,
                    r_vtype,
                    r_disp,
                    r_res,
                ) = struct.unpack("<HQQIBHHBHBBBB", ipl[:34])
                print(
                    f"  Book {r_bid}: version={r_ver}, taskId={r_tid}, wordsCount={r_wcnt}, "
                    f"currIndex={r_cidx}, learnMode={r_lmode}, perTimeSize={r_psize}, result={r_res}",
                    flush=True,
                )
                existing_books.append(
                    {
                        "book_id": r_bid,
                        "book_version": r_ver,
                        "task_id": r_tid,
                        "book_type": r_btype,
                        "words_count": r_wcnt,
                        "curr_index": r_cidx,
                        "learn_mode": r_lmode,
                        "per_time_size": r_psize,
                        "sound_count": r_scnt,
                        "voice_type": r_vtype,
                        "display_content": r_disp,
                    }
                )
    _, yd_curr = await sess.send_ext_msg(b"\x19\x00", expect_msg_type=0x001A, timeout=4.0)
    if yd_curr and len(yd_curr["payload"]) >= 33:
        cpl = yd_curr["payload"]
        _, c_bid, c_ver, c_tid, c_btype, c_wcnt, c_cidx = struct.unpack("<HQQIBHH", cpl[:27])
        print(
            f"GetCurrBookResultMsg (0x001A): currBookId={c_bid}, wordsCount={c_wcnt}, currIndex={c_cidx}",
            flush=True,
        )
    return existing_books


async def cmd_scan(timeout: float = 8.0):
    from bleak import BleakScanner

    print(f"Scanning BLE for {timeout:.1f}s...", flush=True)
    devices = await BleakScanner.discover(timeout=timeout, return_adv=True)
    found = 0
    for d, adv in devices.values():
        name = d.name or adv.local_name or ""
        uuids = [u.lower() for u in (adv.service_uuids or [])]
        if name.startswith("YDW:") or UUID_SERVICE in uuids:
            print(f"  [MATCH] {d.address}  name={name!r}  RSSI={adv.rssi}  uuids={uuids}")
            found += 1
    if not found:
        print("  No YDW012 devices found. Make sure the word card screen is awake.")


async def cmd_info(addr: Optional[str]):
    from bleak import BleakClient

    target = await resolve_device(addr)
    async with BleakClient(target, timeout=15.0) as client:
        sess = YDW012Session(client)
        await sess.authenticate_and_init()
        await query_device_books(sess)
        await client.stop_notify(UUID_NOTIFY)


async def cmd_ls(addr: Optional[str]):
    from bleak import BleakClient

    target = await resolve_device(addr)
    async with BleakClient(target, timeout=15.0) as client:
        sess = YDW012Session(client)
        await sess.authenticate_and_init()
        print("\n--- FAT Root Directory (/) ---", flush=True)
        root_entries = await sess.browse_dir([0])
        for e in root_entries:
            kind = "FILE" if e["is_file"] else "DIR "
            print(f"  [{kind}] {e['name']:<16} cluster={e['cluster']}")
            if not e["is_file"]:
                sub_entries = await sess.browse_dir([0, e["cluster"]])
                for sub in sub_entries:
                    skind = "FILE" if sub["is_file"] else "DIR "
                    print(f"    [{skind}] /{e['name']}/{sub['name']:<14} cluster={sub['cluster']}")
                    if not sub["is_file"]:
                        leaf_entries = await sess.browse_dir([0, e["cluster"], sub["cluster"]])
                        for leaf in leaf_entries:
                            lkind = "FILE" if leaf["is_file"] else "DIR "
                            print(
                                f"      [{lkind}] /{e['name']}/{sub['name']}/{leaf['name']:<12} cluster={leaf['cluster']}"
                            )
        await client.stop_notify(UUID_NOTIFY)


async def cmd_pull(addr: Optional[str], cluster: int, out_path: str):
    from bleak import BleakClient

    target = await resolve_device(addr)
    async with BleakClient(target, timeout=15.0) as client:
        sess = YDW012Session(client)
        await sess.authenticate_and_init()
        print(f"Pulling cluster {cluster} -> {out_path}...", flush=True)
        data = await sess.pull_file_by_cluster(cluster)
        with open(out_path, "wb") as f:
            f.write(data)
        print(f"Saved {len(data)} bytes to {out_path} (CRC16=0x{crc16_xmodem(data):04X})", flush=True)
        await client.stop_notify(UUID_NOTIFY)


async def cmd_upload(
    addr: Optional[str],
    books_to_upload: List[Tuple[int, str, str]],
    daily_words: int = 15,
    keep_existing: bool = True,
):
    from bleak import BleakClient

    compiled = []
    for book_id, title, json_path in books_to_upload:
        entries = format_bilingual_entries(json_path)
        cad_bytes = build_cad(entries, book_id, title)
        rev_bytes = build_rev(entries, book_id, daily_words)
        compiled.append((book_id, title, len(entries), cad_bytes, rev_bytes))

    target = await resolve_device(addr)
    async with BleakClient(target, timeout=15.0) as client:
        sess = YDW012Session(client)
        await sess.authenticate_and_init()
        existing = await query_device_books(sess)

        new_ids = {b[0] for b in compiled}
        books_list = [
            {
                "book_id": bid,
                "book_version": 1681960781000,
                "task_id": bid,
                "book_type": 1,
                "words_count": wcnt,
                "curr_index": 0,
                "learn_mode": 1,
                "per_time_size": daily_words,
                "sound_count": 1,
                "voice_type": 2,
                "display_content": 0,
            }
            for bid, _, wcnt, _, _ in compiled
        ]
        if keep_existing:
            for eb in existing:
                if eb["book_id"] not in new_ids and len(books_list) < 4:
                    books_list.append(eb)

        print("\n--- Sending BeginSyncMsg (0x0055) ---", flush=True)
        _, yd_beg = await sess.send_ext_msg(b"\x55\x00", expect_msg_type=0x0056, timeout=5.0)
        if yd_beg:
            print(f"BeginSyncResultMsg (0x0056): {yd_beg['payload'].hex()}", flush=True)

        print(f"\n--- Sending SetWordBookMsg (0x0075) for books {[b['book_id'] for b in books_list]} ---", flush=True)
        set_msg = pack_SetWordBookMsg(books_list, curr_book_id=compiled[0][0], curr_book_type=1)
        _, yd_set_res = await sess.send_ext_msg(set_msg, expect_msg_type=0x0076, timeout=6.0)
        if yd_set_res:
            print(f"SetWordBookResultMsg (0x0076): {yd_set_res['payload'].hex()}", flush=True)

        for bid, title, wcnt, cad_bytes, rev_bytes in compiled:
            print(f"\n--- Transporting Book {bid} ({title}, {wcnt} words) ---", flush=True)
            tb_msg = pack_TransportBookMsg(book_id=bid, book_type=1, file_mask=3)
            _, yd_tb = await sess.send_ext_msg(tb_msg, expect_msg_type=0x007B, timeout=6.0)
            if yd_tb:
                print(f"TransportBookResultMsg (0x007B) for {bid}: {yd_tb['payload'].hex()}", flush=True)
            await sess.upload_file(f"{bid}.cad", cad_bytes)
            await asyncio.sleep(0.3)
            await sess.upload_file(f"{bid}.rev", rev_bytes)
            await asyncio.sleep(0.5)

        print("\n--- Sending EndSyncMsg (0x00AA, type=0) ---", flush=True)
        _, yd_end = await sess.send_ext_msg(b"\xAA\x00\x00\x00", expect_msg_type=0x00AB, timeout=6.0)
        if yd_end:
            print(f"EndSyncResultMsg (0x00AB): {yd_end['payload'].hex()}", flush=True)

        await asyncio.sleep(0.5)
        await query_device_books(sess)
        await client.stop_notify(UUID_NOTIFY)


def main():
    repo_root = pathlib.Path(__file__).resolve().parent
    default_opt = str(repo_root / "examples" / "sim4options_words.json")
    default_dir = str(repo_root / "examples" / "sim4director_words.json")

    parser = argparse.ArgumentParser(
        description="Generic Dual-Mode BLE RCSP E-Ink Word Card Standalone Sync Tool & Compiler (For Educational & Interoperability Study)"
    )
    parser.add_argument(
        "--addr",
        default=os.environ.get("YDW012_ADDR", "auto"),
        help="BLE MAC address (e.g. XX:XX:XX:XX:XX:XX) or 'auto' to scan by 'YDW:' prefix",
    )
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("scan", help="Scan for nearby YDW012 BLE word cards")
    sub.add_parser("info", help="Connect, authenticate, and query active wordbooks on card")
    sub.add_parser("status", help="Alias for 'info'")
    sub.add_parser("ls", help="Browse the FAT filesystem on the YDW012 card")

    p_pull = sub.add_parser("pull", help="Download a file from the card by FAT cluster ID")
    p_pull.add_argument("cluster", type=int, help="FAT cluster ID from 'ls'")
    p_pull.add_argument("output", help="Output file path")

    p_build = sub.add_parser("build", help="Compile a JSON word list into <book_id>.cad and <book_id>.rev")
    p_build.add_argument("--json", required=True, help="Input JSON word list")
    p_build.add_argument("--book-id", type=int, default=901, help="Numeric book ID (e.g. 901)")
    p_build.add_argument("--title", required=True, help="Book title displayed on the E-Ink screen")
    p_build.add_argument("--daily", type=int, default=15, help="Words per group/session (default: 15)")
    p_build.add_argument("--out-dir", default=".", help="Output directory for .cad and .rev files")

    p_inspect = sub.add_parser("inspect", help="Parse and verify a .cad or .rev binary file")
    p_inspect.add_argument("file", help="Path to .cad or .rev file")

    p_up = sub.add_parser("upload", help="Compile and upload custom wordbooks to YDW012 over BLE")
    p_up.add_argument(
        "--book",
        action="append",
        nargs=3,
        metavar=("BOOK_ID", "TITLE", "JSON_PATH"),
        help="Specify book(s) to upload: --book 901 'sim4options期权双语' examples/sim4options_words.json",
    )
    p_up.add_argument("--daily", type=int, default=15, help="Words per group/session (default: 15)")
    p_up.add_argument("--replace-all", action="store_true", help="Do not keep existing books on card")

    args = parser.parse_args()
    cmd = args.cmd or "upload"

    if cmd == "scan":
        asyncio.run(cmd_scan())
    elif cmd in ("info", "status"):
        asyncio.run(cmd_info(args.addr))
    elif cmd == "ls":
        asyncio.run(cmd_ls(args.addr))
    elif cmd == "pull":
        asyncio.run(cmd_pull(args.addr, args.cluster, args.output))
    elif cmd == "build":
        entries = format_bilingual_entries(args.json)
        cad = build_cad(entries, args.book_id, args.title)
        rev = build_rev(entries, args.book_id, args.daily)
        out_dir = pathlib.Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        cad_path = out_dir / f"{args.book_id}.cad"
        rev_path = out_dir / f"{args.book_id}.rev"
        cad_path.write_bytes(cad)
        rev_path.write_bytes(rev)
        print(
            f"Built {cad_path} ({len(cad)} B, CRC16=0x{crc16_xmodem(cad):04X}) "
            f"& {rev_path} ({len(rev)} B, CRC16=0x{crc16_xmodem(rev):04X}) for {len(entries)} words."
        )
    elif cmd == "inspect":
        p = pathlib.Path(args.file)
        raw = p.read_bytes()
        if p.suffix.lower() == ".cad":
            info = parse_cad(raw)
            print(
                f"[CAD] book_id={info['book_id']} title={info['title']!r} "
                f"words={info['words_count']} size={len(raw)}B CRC16=0x{crc16_xmodem(raw):04X}"
            )
            for i, e in enumerate(info["entries"][:3]):
                print(f"  Sample #{i+1}: {e['headword']} -> {e['definition'].splitlines()[0]}")
        else:
            info = parse_rev(raw)
            print(
                f"[REV] book_id={info['book_id']} words={info['words_count']} "
                f"daily={info['daily_words']} days={len(info['days'])} size={len(raw)}B CRC16=0x{crc16_xmodem(raw):04X}"
            )
    elif cmd == "upload":
        if args.book:
            books = [(int(b[0]), b[1], b[2]) for b in args.book]
        else:
            books = [
                (901, "sim4options期权双语", default_opt),
                (902, "sim4director导演双语", default_dir),
            ]
        asyncio.run(cmd_upload(args.addr, books, daily_words=args.daily, keep_existing=not args.replace_all))


if __name__ == "__main__":
    main()
