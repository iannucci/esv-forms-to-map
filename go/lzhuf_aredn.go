package lzhuf_aredn

import (
	"bytes"
	"fmt"
	"io"
	"os"

	"github.com/la5nta/wl2k-go/lzhuf"
)

var testdataPath = "testdata/"

func DecompressFile(filename string) []byte {
	filePath := testdataPath + "/" + filename
	file, err := os.Open(filePath)
	if err != nil {
		fmt.Printf("Error reading file from path %s: %v\n", filePath, err)
		return nil
	}

	defer file.Close() // make sure to close the file after reading

	decompressing_reader, err := lzhuf.NewB2Reader(file)
	if err != nil {
		fmt.Printf("NewB2Reader creation error: %v", err)
		return nil
	}

	decompressed_data, err := io.ReadAll(decompressing_reader)
	if err != nil {
		fmt.Printf("Reading error: %v", err)
		return nil
	}

	fmt.Printf("Read: %s", string(decompressed_data))

	return decompressed_data
}

func DecompressBuffer(buf bytes.Buffer) []byte {

	lzwReader, err := lzhuf.NewB2Reader(&buf)
	if err != nil {
		fmt.Printf("NewB2Reader error: %v", err)
		return nil
	}

	decompressed_data, err := io.ReadAll(lzwReader)
	if err != nil {
		fmt.Printf("Failed to read decompressed data: %v", err)
		return nil
	}

	return decompressed_data
}
