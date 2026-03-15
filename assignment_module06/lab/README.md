# Multi-Agent Report Pipeline (C-Lock Emissions)

## How It Works

The multi-agent system fetches raw emissions CSV from the C-Lock API, then runs three LLM agents in sequence. **Agent 1** acts as a methane data analyst: it extracts methane-related columns and metadata from the CSV and organizes them into a markdown table. **Agent 2** receives that table and produces an analysis report covering the feeder ID, top 5 visitors by visit count, and CH4 emission statistics (mean, median, variation). **Agent 3** takes the report and extracts the most important information for methane mitigation—priorities, actionable recommendations, and key metrics to track.

## What It Does

The pipeline turns raw C-Lock GreenFeed emissions data into a concise, actionable summary for livestock methane reduction. Each agent has a distinct role (extract → analyze → prioritize), and information flows from one to the next. The system uses the OpenAI API (gpt-4o-mini) with system prompts to define each agent’s behavior and user prompts to pass the data.
