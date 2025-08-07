package lzhuf_aredn

import (
	"testing"
)

func TestDecompressFile(t *testing.T) {
	filename := "G5QTMOJYMY4W-with-crc16"
	data := DecompressFile(filename)
	if data == nil {
		t.Errorf("Failed to decode file %s", filename)
	} else {
		t.Logf("Successfully decoded file %s, data length: %d bytes", filename, len(data))
		t.Logf("Decompressed data: %s", string(data))
	}
}
