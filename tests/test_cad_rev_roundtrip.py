#!/usr/bin/env python3
"""
Unit & Round-Trip Verification Tests for YDW012 Protocol, Crypto, and .CAD/.REV Compiler.
"""

import pathlib
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ydw012_cli import (
    build_cad,
    build_rev,
    crc16_xmodem,
    format_bilingual_entries,
    get_encrypted_auth_data,
    pack_rcsp_cmd,
    pack_rcsp_resp,
    pack_SetWordBookMsg,
    pack_TransportBookMsg,
    parse_cad,
    parse_rev,
)


class TestYDW012CompilerAndProtocol(unittest.TestCase):
    def test_jl_auth_deterministic(self):
        challenge = bytes([0x00] + list(range(16)))
        resp1 = get_encrypted_auth_data(challenge)
        resp2 = get_encrypted_auth_data(challenge)
        self.assertEqual(len(resp1), 17)
        self.assertEqual(resp1[0], 0x01)
        self.assertEqual(resp1, resp2)

    def test_rcsp_framing(self):
        cmd03 = pack_rcsp_cmd(0x03, b"\xFF\xFF\xFF\xFF\x00", sn=1, has_resp=True)
        self.assertEqual(cmd03[:3], b"\xFE\xDC\xBA")
        self.assertEqual(cmd03[-1], 0xEF)
        self.assertEqual(cmd03[3], 0xC0)  # is_cmd | has_resp
        self.assertEqual(cmd03[4], 0x03)

        resp20 = pack_rcsp_resp(0x20, status=0, sn=5, param=b"901.cad\x00\x00")
        self.assertEqual(resp20[:3], b"\xFE\xDC\xBA")
        self.assertEqual(resp20[3], 0x00)
        self.assertEqual(resp20[4], 0x20)
        self.assertEqual(resp20[-1], 0xEF)

    def test_sim4options_roundtrip(self):
        opt_json = REPO_ROOT / "examples" / "sim4options_words.json"
        entries = format_bilingual_entries(str(opt_json))
        self.assertEqual(len(entries), 130)

        cad = build_cad(entries, 901, "sim4options期权双语")
        self.assertEqual(len(cad), 50164)
        parsed_cad = parse_cad(cad)
        self.assertEqual(parsed_cad["book_id"], 901)
        self.assertEqual(parsed_cad["title"], "sim4options期权双语")
        self.assertEqual(parsed_cad["words_count"], 130)
        self.assertEqual(parsed_cad["entries"], entries)

        rev = build_rev(entries, 901, 15)
        self.assertEqual(len(rev), 5252)
        parsed_rev = parse_rev(rev)
        self.assertEqual(parsed_rev["book_id"], 901)
        self.assertEqual(parsed_rev["words_count"], 130)
        self.assertEqual(parsed_rev["daily_words"], 15)
        self.assertEqual(parsed_rev["headwords"], [e["headword"] for e in entries])

    def test_sim4director_roundtrip(self):
        dir_json = REPO_ROOT / "examples" / "sim4director_words.json"
        entries = format_bilingual_entries(str(dir_json))
        self.assertEqual(len(entries), 341)

        cad = build_cad(entries, 902, "sim4director导演双语")
        self.assertEqual(len(cad), 110198)
        parsed_cad = parse_cad(cad)
        self.assertEqual(parsed_cad["book_id"], 902)
        self.assertEqual(parsed_cad["title"], "sim4director导演双语")
        self.assertEqual(parsed_cad["words_count"], 341)
        self.assertEqual(parsed_cad["entries"], entries)

        rev = build_rev(entries, 902, 15)
        self.assertEqual(len(rev), 15380)
        parsed_rev = parse_rev(rev)
        self.assertEqual(parsed_rev["book_id"], 902)
        self.assertEqual(parsed_rev["words_count"], 341)
        self.assertEqual(parsed_rev["headwords"], [e["headword"] for e in entries])

    def test_youdao_msg_packers(self):
        msg75 = pack_SetWordBookMsg(
            [{"book_id": 901, "words_count": 130}, {"book_id": 902, "words_count": 341}],
            curr_book_id=901,
        )
        self.assertEqual(len(msg75), 4 + 2 * 31 + 9)
        msg7a = pack_TransportBookMsg(901, 1, 3)
        self.assertEqual(len(msg7a), 12)
        self.assertGreater(crc16_xmodem(msg75), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
