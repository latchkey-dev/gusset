package main

type Greeter struct {
	Name string
}

type Speaker interface {
	Speak() string
}

func (g Greeter) Greet() string {
	return decorate(g.Name)
}

func (g *Greeter) Rename(n string) {
	g.Name = n
}

func decorate(s string) string {
	return "** " + s + " **"
}

func Unused() string {
	return "never called"
}
