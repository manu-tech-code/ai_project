package com.alm.parser.dto;

import java.util.List;
import java.util.Map;

/**
 * Top-level parse result returned to callers.
 *
 * @param nodes  UCG node descriptors (serialised as plain maps for forward-compatibility).
 * @param edges  UCG edge descriptors.
 * @param errors Non-fatal per-file error messages collected during the walk.
 */
public record ParseResponse(
        List<Map<String, Object>> nodes,
        List<Map<String, Object>> edges,
        List<String> errors
) {}
