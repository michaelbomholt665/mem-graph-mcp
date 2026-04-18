package main

import (
	"context"
	"fmt"
	"sync"
)

// Animal defines the interface for animals.
type Animal interface {
	Speak() string
	Name() string
}

// Dog is a concrete animal.
type Dog struct {
	name string
	age  int
}

// Speak implements Animal.
func (d *Dog) Speak() string {
	return fmt.Sprintf("Woof, I am %s", d.name)
}

// Name implements Animal.
func (d *Dog) Name() string {
	return d.name
}

// NewDog constructs a Dog.
func NewDog(name string, age int) *Dog {
	return &Dog{name: name, age: age}
}

// Greet returns a greeting string.
func Greet(name string) string {
	return fmt.Sprintf("Hello, %s!", name)
}

// FetchData fetches data from a URL using a goroutine pattern.
func FetchData(ctx context.Context, url string) ([]byte, error) {
	ch := make(chan []byte, 1)
	errCh := make(chan error, 1)

	go func() {
		defer close(ch)
		// simulated fetch
		ch <- []byte("data")
	}()

	select {
	case data := <-ch:
		return data, nil
	case err := <-errCh:
		return nil, err
	case <-ctx.Done():
		return nil, ctx.Err()
	}
}

// ProcessItems transforms a slice.
func ProcessItems(items []int) []int {
	result := make([]int, 0, len(items))
	var mu sync.Mutex
	for _, item := range items {
		mu.Lock()
		if item > 0 {
			result = append(result, item*2)
		}
		mu.Unlock()
	}
	return result
}

func main() {
	dog := NewDog("Rex", 3)
	fmt.Println(dog.Speak())

	ctx := context.Background()
	data, err := FetchData(ctx, "https://example.com")
	if err != nil {
		panic(err)
	}
	_ = data
}
