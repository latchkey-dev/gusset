package main

import "fmt"

func main() {
	g := Greeter{Name: "world"}
	g.Rename("mundo")
	fmt.Println(report(g.Greet()))
}

func report(s string) string {
	return "[" + s + "]"
}
