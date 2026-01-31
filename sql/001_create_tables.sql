-- Quiz Please Game Stats Database Schema
-- This schema stores game metadata, teams, participations, and round scores

-- Create schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS quizplease;

-- Set search path to use the quizplease schema
SET search_path TO quizplease, public;

-- Games table: stores metadata about each quiz game
CREATE TABLE IF NOT EXISTS quizplease.games (
    id INTEGER PRIMARY KEY,
    game_date DATE NOT NULL,
    game_time VARCHAR(10),
    venue VARCHAR(255),
    category VARCHAR(100),
    game_name VARCHAR(255),
    game_number VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index on game_date for faster date range queries
CREATE INDEX IF NOT EXISTS idx_games_date ON quizplease.games(game_date DESC);
CREATE INDEX IF NOT EXISTS idx_games_category ON quizplease.games(category);

-- Teams table: stores unique team names
CREATE TABLE IF NOT EXISTS quizplease.teams (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index on team name for faster lookups
CREATE INDEX IF NOT EXISTS idx_teams_name ON quizplease.teams(name);

-- Team game participations: links teams to games with their ranking
CREATE TABLE IF NOT EXISTS quizplease.team_game_participations (
    id SERIAL PRIMARY KEY,
    game_id INTEGER NOT NULL REFERENCES quizplease.games(id) ON DELETE CASCADE,
    team_id INTEGER NOT NULL REFERENCES quizplease.teams(id) ON DELETE CASCADE,
    rank INTEGER,
    total_score NUMERIC(5, 1),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(game_id, team_id)
);

-- Create indexes for faster joins and queries
CREATE INDEX IF NOT EXISTS idx_participations_game ON quizplease.team_game_participations(game_id);
CREATE INDEX IF NOT EXISTS idx_participations_team ON quizplease.team_game_participations(team_id);
CREATE INDEX IF NOT EXISTS idx_participations_rank ON quizplease.team_game_participations(rank);

-- Round scores: stores individual round scores for each team participation
CREATE TABLE IF NOT EXISTS quizplease.round_scores (
    id SERIAL PRIMARY KEY,
    participation_id INTEGER NOT NULL REFERENCES quizplease.team_game_participations(id) ON DELETE CASCADE,
    round_name VARCHAR(100) NOT NULL,
    score NUMERIC(5, 1),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(participation_id, round_name)
);

-- Create index for faster queries by participation
CREATE INDEX IF NOT EXISTS idx_round_scores_participation ON quizplease.round_scores(participation_id);

-- Add comments for documentation
COMMENT ON SCHEMA quizplease IS 'Quiz Please game statistics schema';
COMMENT ON TABLE quizplease.games IS 'Stores metadata about each quiz game';
COMMENT ON TABLE quizplease.teams IS 'Stores unique team names';
COMMENT ON TABLE quizplease.team_game_participations IS 'Links teams to games with their ranking and total score';
COMMENT ON TABLE quizplease.round_scores IS 'Stores individual round scores for each team participation';
