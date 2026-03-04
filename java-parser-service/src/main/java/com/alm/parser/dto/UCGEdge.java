package com.alm.parser.dto;

import java.util.Map;

/**
 * Unified Code Graph directed edge.
 *
 * @param source   ID of the originating node.
 * @param target   ID of the destination node.
 * @param type     Relationship kind: contains, inherits, implements, calls, imports, data_flow.
 * @param metadata Additional properties (e.g. method_name for call edges).
 */
public record UCGEdge(
        String source,
        String target,
        String type,
        Map<String, Object> metadata
) {}
