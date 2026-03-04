package com.alm.parser.dto;

/**
 * Incoming parse request. {@code repoPath} is the absolute path on the
 * server filesystem to the Java source root that should be analysed.
 */
public record ParseRequest(String repoPath) {}
