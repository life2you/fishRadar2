package generation

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"os/exec"
	"path/filepath"
)

type RefreshPromptRequest struct {
	TaskName       string `json:"task_name"`
	Keyword        string `json:"keyword"`
	Description    string `json:"description"`
	BasePromptFile string `json:"base_prompt_file"`
}

type PromptPayload struct {
	AIPromptBaseFile     string  `json:"ai_prompt_base_file"`
	AIPromptCriteriaFile string  `json:"ai_prompt_criteria_file"`
	AIPromptBaseText     *string `json:"ai_prompt_base_text"`
	AIPromptCriteriaText *string `json:"ai_prompt_criteria_text"`
	AIPromptText         *string `json:"ai_prompt_text"`
}

func (s *Service) RefreshPrompt(ctx context.Context, payload RefreshPromptRequest) (*PromptPayload, error) {
	workerRoot, err := filepath.Abs(s.cfg.WorkerPyRoot)
	if err != nil {
		return nil, err
	}
	command := exec.CommandContext(ctx, s.cfg.PythonBin, "tools/task_prompt_refresh_bridge.py")
	command.Dir = workerRoot
	command.Env = append(command.Environ(), "PYTHONIOENCODING=utf-8", "PYTHONUNBUFFERED=1")
	stdin, err := command.StdinPipe()
	if err != nil {
		return nil, err
	}
	stdout, err := command.StdoutPipe()
	if err != nil {
		return nil, err
	}
	command.Stderr = command.Stdout
	if err := command.Start(); err != nil {
		return nil, err
	}

	go func() {
		defer stdin.Close()
		_ = json.NewEncoder(stdin).Encode(payload)
	}()

	scanner := bufio.NewScanner(stdout)
	for scanner.Scan() {
		var event map[string]json.RawMessage
		if err := json.Unmarshal(scanner.Bytes(), &event); err != nil {
			continue
		}
		var eventType string
		if err := json.Unmarshal(event["type"], &eventType); err != nil {
			continue
		}
		switch eventType {
		case "result":
			var wrapper struct {
				Payload PromptPayload `json:"payload"`
			}
			if err := json.Unmarshal(scanner.Bytes(), &wrapper); err == nil {
				if err := command.Wait(); err != nil {
					return nil, err
				}
				return &wrapper.Payload, nil
			}
		case "error":
			var wrapper struct {
				Error string `json:"error"`
			}
			_ = json.Unmarshal(scanner.Bytes(), &wrapper)
			_ = command.Wait()
			if wrapper.Error == "" {
				wrapper.Error = "AI 标准刷新失败"
			}
			return nil, fmt.Errorf("%s", wrapper.Error)
		}
	}
	if err := scanner.Err(); err != nil {
		return nil, err
	}
	if err := command.Wait(); err != nil {
		return nil, err
	}
	return nil, fmt.Errorf("AI 标准刷新未返回结果")
}
