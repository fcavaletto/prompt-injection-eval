// Renders chat prompts with Ollama's own template and renderer packages.
//
// It mirrors server.renderPrompt in Ollama v0.34.4: a model whose config names a
// renderer goes through renderers.RenderWithRenderer; every other model goes
// through its Go template. Nothing else the server does is exercised here: no
// truncation to the context window, no tokenization, no generation.
//
// Input (stdin):  {"jobs": [{"id": "...", "template": "...", "renderer": "",
//                            "messages": [...], "tools": [...]}]}
// Output (stdout): [{"id": "...", "prompt": "...", "error": ""}]
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"

	"github.com/ollama/ollama/api"
	"github.com/ollama/ollama/model/renderers"
	"github.com/ollama/ollama/template"
)

type job struct {
	ID       string        `json:"id"`
	Template string        `json:"template"`
	Renderer string        `json:"renderer"`
	Messages []api.Message `json:"messages"`
	Tools    []api.Tool    `json:"tools"`
}

type result struct {
	ID     string `json:"id"`
	Prompt string `json:"prompt"`
	Error  string `json:"error"`
}

func render(j job) (string, error) {
	if j.Renderer != "" {
		return renderers.RenderWithRenderer(j.Renderer, j.Messages, j.Tools, nil)
	}
	t, err := template.Parse(j.Template)
	if err != nil {
		return "", err
	}
	var b bytes.Buffer
	if err := t.Execute(&b, template.Values{Messages: j.Messages, Tools: j.Tools}); err != nil {
		return "", err
	}
	return b.String(), nil
}

func main() {
	var in struct {
		Jobs []job `json:"jobs"`
	}
	if err := json.NewDecoder(os.Stdin).Decode(&in); err != nil {
		fmt.Fprintln(os.Stderr, "bad input:", err)
		os.Exit(2)
	}
	out := make([]result, 0, len(in.Jobs))
	for _, j := range in.Jobs {
		r := result{ID: j.ID}
		p, err := render(j)
		if err != nil {
			r.Error = err.Error()
		}
		r.Prompt = p
		out = append(out, r)
	}
	enc := json.NewEncoder(os.Stdout)
	enc.SetEscapeHTML(false)
	if err := enc.Encode(out); err != nil {
		fmt.Fprintln(os.Stderr, "bad output:", err)
		os.Exit(2)
	}
}
