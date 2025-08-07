package lzhuf_aredn

import (
	"fmt"
	"os"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Println("No filename provided")
		return
	}
	filename := os.Args[1]
	DecompressFile(filename) // side effect is decompressed file in the same folder as the source file
	fmt.Printf("Decompressed file %s successfully.\n", filename)
}
