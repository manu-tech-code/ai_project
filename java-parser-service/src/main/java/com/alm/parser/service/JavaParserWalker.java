package com.alm.parser.service;

import com.alm.parser.dto.ParseResponse;
import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.EnumDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.expr.FieldAccessExpr;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.symbolsolver.JavaSymbolSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.CombinedTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.JavaParserTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.ReflectionTypeSolver;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;

/**
 * Walks every {@code .java} source file under a repository root and builds a
 * Unified Code Graph (UCG) expressed as lists of node and edge descriptor maps.
 *
 * <p>The graph covers:
 * <ul>
 *   <li>Module (file) nodes</li>
 *   <li>Class / interface nodes with modifiers, annotations, supertype, LOC</li>
 *   <li>Method (function) nodes with return type, parameters, JDBC / getter-setter flags</li>
 *   <li>Field nodes</li>
 *   <li>Enum nodes with entry names</li>
 *   <li>Edges: contains, imports, inherits, implements, calls, data_flow</li>
 * </ul>
 *
 * <p>Parse failures on individual files are collected into the {@code errors} list and
 * processing continues rather than aborting the whole walk.
 */
@Service
public class JavaParserWalker {

    private static final Logger log = LoggerFactory.getLogger(JavaParserWalker.class);

    /**
     * Entry point: configure the symbol solver, walk the file tree and return the UCG.
     *
     * @param repoPath absolute path to the repository / source root on the server filesystem
     * @return a {@link ParseResponse} containing nodes, edges and any per-file errors
     * @throws IOException if the root directory cannot be walked
     */
    public ParseResponse walkRepository(String repoPath) throws IOException {

        List<Map<String, Object>> nodes = new ArrayList<>();
        List<Map<String, Object>> edges = new ArrayList<>();
        List<String> errors = new ArrayList<>();

        // ------------------------------------------------------------------ symbol solver
        CombinedTypeSolver typeSolver = new CombinedTypeSolver();
        typeSolver.add(new ReflectionTypeSolver());

        // JavaParserTypeSolver needs the actual source root, not an arbitrary sub-directory.
        // We add it best-effort; if it fails we still continue with reflection-only resolution.
        try {
            typeSolver.add(new JavaParserTypeSolver(new File(repoPath)));
        } catch (Exception e) {
            log.warn("Could not configure JavaParserTypeSolver for {}: {}", repoPath, e.getMessage());
        }

        JavaSymbolSolver symbolSolver = new JavaSymbolSolver(typeSolver);
        StaticJavaParser.getParserConfiguration()
                .setSymbolResolver(symbolSolver)
                .setLanguageLevel(ParserConfiguration.LanguageLevel.JAVA_21);

        // ------------------------------------------------------------------ file walk
        Path root = Path.of(repoPath);
        try (Stream<Path> paths = Files.walk(root)) {
            paths.filter(p -> p.toString().endsWith(".java"))
                 .filter(p -> !p.toString().contains("/test/"))
                 .forEach(javaFile -> {
                     try {
                         parseFile(javaFile, root, nodes, edges, errors);
                     } catch (Exception e) {
                         String msg = "Error parsing " + javaFile + ": " + e.getMessage();
                         log.warn(msg);
                         errors.add(msg);
                     }
                 });
        }

        log.info("Walk complete for {}: {} nodes, {} edges, {} errors",
                repoPath, nodes.size(), edges.size(), errors.size());
        return new ParseResponse(nodes, edges, errors);
    }

    // ======================================================================= per-file parsing

    private void parseFile(
            Path file,
            Path root,
            List<Map<String, Object>> nodes,
            List<Map<String, Object>> edges,
            List<String> errors) {

        CompilationUnit cu;
        try {
            cu = StaticJavaParser.parse(file);
        } catch (Exception e) {
            String msg = "Parse failure in " + file + ": " + e.getMessage();
            log.warn(msg);
            errors.add(msg);
            return;
        }

        String relPath = root.relativize(file).toString();

        // ------------------------------------------------------------------ module node
        String moduleId = "java:module:" + relPath;
        String packageName = cu.getPackageDeclaration()
                .map(p -> p.getNameAsString())
                .orElse("");

        nodes.add(nodeMap(
                moduleId, "module", relPath, relPath,
                1, cu.getRange().map(r -> r.end.line).orElse(0),
                Map.of("package", packageName)
        ));

        // ------------------------------------------------------------------ import edges
        cu.getImports().forEach(imp -> {
            String importName = imp.getNameAsString();
            edges.add(edgeMap(
                    moduleId,
                    "java:type:" + importName,
                    "imports",
                    Map.of("static", imp.isStatic(), "asterisk", imp.isAsterisk())
            ));
        });

        // ------------------------------------------------------------------ classes / interfaces
        cu.findAll(ClassOrInterfaceDeclaration.class).forEach(cls ->
                processClass(cls, moduleId, relPath, nodes, edges));

        // ------------------------------------------------------------------ enums
        cu.findAll(EnumDeclaration.class).forEach(en -> {
            String enumId = "java:enum:" + relPath + ":" + en.getNameAsString();
            List<String> entries = en.getEntries().stream()
                    .map(e -> e.getNameAsString())
                    .toList();

            nodes.add(nodeMap(
                    enumId, "enum", en.getNameAsString(), relPath,
                    en.getRange().map(r -> r.begin.line).orElse(0),
                    en.getRange().map(r -> r.end.line).orElse(0),
                    Map.of("entries", entries)
            ));
            edges.add(edgeMap(moduleId, enumId, "contains", Map.of()));
        });
    }

    // ======================================================================= class processing

    private void processClass(
            ClassOrInterfaceDeclaration cls,
            String moduleId,
            String relPath,
            List<Map<String, Object>> nodes,
            List<Map<String, Object>> edges) {

        String nodeType = cls.isInterface() ? "interface" : "class";
        String classId  = "java:" + nodeType + ":" + relPath + ":" + cls.getNameAsString();

        List<String> modifiers = cls.getModifiers().stream()
                .map(m -> m.getKeyword().asString())
                .toList();
        List<String> annotations = cls.getAnnotations().stream()
                .map(a -> a.getNameAsString())
                .toList();
        List<String> implementedInterfaces = cls.getImplementedTypes().stream()
                .map(t -> t.getNameAsString())
                .toList();
        String superclass = cls.getExtendedTypes().stream()
                .findFirst()
                .map(t -> t.getNameAsString())
                .orElse("");

        Map<String, Object> classMeta = new HashMap<>();
        classMeta.put("modifiers", modifiers);
        classMeta.put("annotations", annotations);
        classMeta.put("implements", implementedInterfaces);
        classMeta.put("superclass", superclass);
        classMeta.put("abstract", cls.isAbstract());
        classMeta.put("method_count", cls.getMethods().size());

        nodes.add(nodeMap(
                classId, nodeType, cls.getNameAsString(), relPath,
                cls.getRange().map(r -> r.begin.line).orElse(0),
                cls.getRange().map(r -> r.end.line).orElse(0),
                classMeta
        ));

        // contains: module → class
        edges.add(edgeMap(moduleId, classId, "contains", Map.of()));

        // inherits edge
        cls.getExtendedTypes().forEach(parent -> {
            String parentId = "java:class:" + parent.getNameAsString();
            edges.add(edgeMap(classId, parentId, "inherits", Map.of()));
        });

        // implements edges
        cls.getImplementedTypes().forEach(iface -> {
            String ifaceId = "java:interface:" + iface.getNameAsString();
            edges.add(edgeMap(classId, ifaceId, "implements", Map.of()));
        });

        // methods
        cls.getMethods().forEach(method ->
                processMethod(method, cls.getNameAsString(), classId, relPath, nodes, edges));

        // fields
        cls.getFields().forEach(field ->
                field.getVariables().forEach(var -> {
                    String fieldId = "java:field:" + relPath + ":" + cls.getNameAsString() + "." + var.getNameAsString();
                    nodes.add(nodeMap(
                            fieldId, "field", var.getNameAsString(), relPath,
                            field.getRange().map(r -> r.begin.line).orElse(0),
                            field.getRange().map(r -> r.end.line).orElse(0),
                            Map.of(
                                    "type", field.getElementType().asString(),
                                    "class", cls.getNameAsString()
                            )
                    ));
                    edges.add(edgeMap(classId, fieldId, "contains", Map.of()));
                }));
    }

    // ======================================================================= method processing

    private void processMethod(
            MethodDeclaration method,
            String className,
            String classId,
            String relPath,
            List<Map<String, Object>> nodes,
            List<Map<String, Object>> edges) {

        String methodId = "java:function:" + relPath + ":" + className + "." + method.getNameAsString();

        List<String> paramTypes = method.getParameters().stream()
                .map(p -> p.getTypeAsString())
                .toList();
        List<String> methodAnnotations = method.getAnnotations().stream()
                .map(a -> a.getNameAsString())
                .toList();
        List<String> methodModifiers = method.getModifiers().stream()
                .map(m -> m.getKeyword().asString())
                .toList();

        int methodLoc = method.getRange()
                .map(r -> r.end.line - r.begin.line + 1)
                .orElse(0);

        Map<String, Object> methodMeta = new HashMap<>();
        methodMeta.put("class", className);
        methodMeta.put("return_type", method.getTypeAsString());
        methodMeta.put("parameters", paramTypes);
        methodMeta.put("annotations", methodAnnotations);
        methodMeta.put("modifiers", methodModifiers);
        methodMeta.put("loc", methodLoc);
        methodMeta.put("has_jdbc", containsJdbc(method));
        methodMeta.put("is_getter_setter", isGetterSetter(method.getNameAsString()));

        nodes.add(nodeMap(
                methodId, "function", method.getNameAsString(), relPath,
                method.getRange().map(r -> r.begin.line).orElse(0),
                method.getRange().map(r -> r.end.line).orElse(0),
                methodMeta
        ));

        // contains: class → method
        edges.add(edgeMap(classId, methodId, "contains", Map.of()));

        // call edges (best-effort — only when an explicit scope qualifier is present)
        method.findAll(MethodCallExpr.class).forEach(call ->
                call.getScope().ifPresent(scope -> {
                    String calleeId = "java:function:" + scope + "." + call.getNameAsString();
                    edges.add(edgeMap(
                            methodId, calleeId, "calls",
                            Map.of("method_name", call.getNameAsString())
                    ));
                }));

        // field-access / data-flow edges
        method.findAll(FieldAccessExpr.class).forEach(field ->
                edges.add(edgeMap(
                        methodId,
                        "java:field:" + field.getNameAsString(),
                        "data_flow",
                        Map.of("field", field.getNameAsString())
                )));
    }

    // ======================================================================= helpers

    /**
     * Builds a node descriptor map using the canonical UCG field names.
     * Using an explicit {@link HashMap} instead of {@link Map#of} so that values
     * can be {@code null}-safe and the map remains mutable if callers need to extend it.
     */
    private static Map<String, Object> nodeMap(
            String id, String type, String name, String filePath,
            int lineStart, int lineEnd, Map<String, Object> metadata) {

        Map<String, Object> m = new HashMap<>();
        m.put("id",         id);
        m.put("type",       type);
        m.put("language",   "java");
        m.put("name",       name);
        m.put("file_path",  filePath);
        m.put("line_start", lineStart);
        m.put("line_end",   lineEnd);
        m.put("metadata",   metadata);
        return m;
    }

    /** Builds an edge descriptor map. */
    private static Map<String, Object> edgeMap(
            String source, String target, String type, Map<String, Object> metadata) {

        Map<String, Object> m = new HashMap<>();
        m.put("source",   source);
        m.put("target",   target);
        m.put("type",     type);
        m.put("metadata", metadata);
        return m;
    }

    /**
     * Heuristic check: does the method body reference common JDBC artefacts?
     * This is intentionally text-based (no full type resolution required) so that
     * it works even when the JDBC driver is not on the classpath.
     */
    private static boolean containsJdbc(MethodDeclaration method) {
        String body = method.toString();
        return body.contains("PreparedStatement")
                || body.contains("ResultSet")
                || body.contains("DriverManager")
                || (body.contains("Connection") && body.contains("getConnection"));
    }

    /**
     * Returns {@code true} when the method name follows the standard Java Bean
     * getter / setter / boolean-accessor convention.
     */
    private static boolean isGetterSetter(String methodName) {
        return methodName.startsWith("get")
                || methodName.startsWith("set")
                || methodName.startsWith("is");
    }
}
