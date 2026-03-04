package com.alm.parser.dto;

import java.util.Map;

/**
 * Unified Code Graph node.
 *
 * @param id        Globally unique node identifier (e.g. {@code java:class:src/Foo.java:Foo}).
 * @param type      One of: module, class, interface, function, field, enum.
 * @param language  Always {@code "java"} for this service.
 * @param name      Simple name of the symbol.
 * @param filePath  Relative path from the repo root.
 * @param lineStart First line of the declaration (1-based).
 * @param lineEnd   Last line of the declaration (1-based).
 * @param metadata  Extra attributes: superclass, interfaces, modifiers, annotations, etc.
 */
public record UCGNode(
        String id,
        String type,
        String language,
        String name,
        String filePath,
        int lineStart,
        int lineEnd,
        Map<String, Object> metadata
) {}
