// Y-POSITION CLUSTERING APPROACH for Facebook group post extraction
// Facebook renders post content as separate dir="auto" blocks
// positioned visually on the page. Blocks close together = same post.
// A gap of 80+ px = new post boundary.
() => {
    const MAX = MAX_POSTS;

    function isGarbled(text) {
        if (!text || text.length < 5) return true;
        const clean = text.replace(/[\w\s.,!?\u00BF\u00A1;:'"()\[\]@#$%&\/+=<>{}\n\r\t\u00C0-\u024F\u0400-\u04FF\u0600-\u06FF\-\u2018\u2019\u201C\u201D\u2026\u2013\u2014\u00AB\u00BB\u20AC\u00A3\u00A5]/g, '');
        return (clean.length / text.length) > 0.35;
    }

    const JUNK_EXACT = new Set([
        'see more', 'see less', 'ver más', 'ver menos', 'voir plus', 'voir moins',
        'like', 'reply', 'share', 'responder', 'compartir', "j'aime", 'partager',
        'follow', 'seguir', 'top contributor', 'miembro destacado', 'original audio',
        'all reactions', 'most relevant', 'newest first', 'highlights',
        'write a comment', 'write a public comment', 'photo', 'video', 'gif',
        'camera', 'create a post', 'invite', 'joined', 'about', 'discussion',
        'featured', 'members', 'media', 'reels', 'events', 'files',
        'send message', 'more', 'menos', 'plus'
    ]);

    function isJunk(text) {
        const t = text.trim();
        if (t.length < 10) return true;
        if (isGarbled(t)) return true;
        if (JUNK_EXACT.has(t.toLowerCase())) return true;
        // Junk prefixes
        if (/^(shared with|compartido con|photos from|fotos de)/i.test(t)) return true;
        if (/^\d+\s*(comments?|comentarios?|replies|respuestas|likes?|reactions?|shares?)/i.test(t)) return true;
        if (/^private group/i.test(t)) return true;
        // Hashtag-only blocks
        if (/^[#\s\w]+$/.test(t) && (t.match(/#/g) || []).length > 2 && t.length < 200) return true;
        // Time-like strings (e.g., "3d", "5h", "1w", "March 15 at 2:30 PM")
        if (/^\d+[dwmhDWMH]$/.test(t)) return true;
        // FB UI / group chrome text
        if (/^(view more|ver m.s|voir plus|recent media|write a|only members|anyone can find|this is a great.{0,30}group)/i.test(t)) return true;
        if (/replied\s*[·.]\s*\d+\s*(repl|resp)/i.test(t)) return true;
        if (/^(rising contributor|new member|admin|moderator)/i.test(t)) return true;
        // Names only (very short, no question marks, likely author labels)
        if (t.length < 30 && !/[?¿!.]/.test(t) && /^[A-Z][a-z]+ [A-Z]/.test(t)) return true;
        return false;
    }

    // Step 1: Collect all visible dir="auto" blocks with Y positions
    const allAuto = document.querySelectorAll('[dir="auto"]');
    const blocks = [];
    for (const b of allAuto) {
        const text = b.textContent.trim();
        if (text.length < 10) continue;
        const rect = b.getBoundingClientRect();
        if (rect.top < -10000) continue;
        if (rect.height < 3 || rect.width < 3) continue;
        blocks.push({ text, y: rect.top, bottom: rect.bottom, h: rect.height, el: b });
    }

    blocks.sort((a, b) => a.y - b.y);

    // Step 2: Cluster by Y-proximity (gap of 40px+ = new post)
    // Tighter gap to avoid merging post + comments + next post
    const GAP = 40;
    const clusters = [];
    let cur = [];

    for (let i = 0; i < blocks.length; i++) {
        if (cur.length === 0) { cur.push(blocks[i]); continue; }
        const prevBottom = Math.max(...cur.map(b => b.bottom));
        if (blocks[i].y - prevBottom > GAP) {
            clusters.push(cur);
            cur = [blocks[i]];
        } else {
            cur.push(blocks[i]);
        }
    }
    if (cur.length > 0) clusters.push(cur);

    // Step 3: Convert clusters to posts
    const posts = [];
    const seenText = new Set();

    for (const cluster of clusters) {
        if (posts.length >= MAX) break;

        // Skip suggested/highlighted/old posts that FB resurfaces
        const clusterText = cluster.map(b => b.text.toLowerCase()).join(' ');
        if (/suggested for you|suggested post|sugerido para ti|post sugerido|publication sugg|suggested group|recommended for you|popular post|post populaire|sponsored|patrocinado/.test(clusterText)) continue;
        // Skip "featured" posts (pinned old content)
        if (/^featured/i.test(clusterText.trim())) continue;
        // Skip posts that contain year-old time markers (FB shows "1y", "2y" for old posts)
        if (/\b[2-9]y\b|\b1y\b|\b\d+\s*years?\s*ago/i.test(clusterText)) continue;

        // Collect non-junk text, dedup substrings
        const parts = [];
        const partSet = new Set();

        for (const block of cluster) {
            const t = block.text;
            if (isJunk(t)) continue;

            let isDupe = false;
            for (const ex of partSet) {
                if (ex.includes(t)) { isDupe = true; break; }
                if (t.includes(ex)) {
                    partSet.delete(ex);
                    const idx = parts.indexOf(ex);
                    if (idx >= 0) parts.splice(idx, 1);
                    break;
                }
            }
            if (isDupe) continue;
            partSet.add(t);
            parts.push(t);
        }

        let text = parts.join(' ').trim();
        if (!text || text.length < 20) continue;
        // Cap at 500 chars — if longer, it's likely merged with comments/UI
        text = text.substring(0, 500);

        const key = text.substring(0, 200);
        if (seenText.has(key)) continue;
        seenText.add(key);

        // Author: walk up from first block to find <strong>
        let author = '';
        if (cluster.length > 0) {
            let el = cluster[0].el;
            for (let i = 0; i < 15; i++) {
                el = el.parentElement;
                if (!el) break;
                const s = el.querySelector('strong');
                if (s) {
                    const name = s.textContent.trim();
                    const lower = name.toLowerCase();
                    if (name.length > 1 && name.length < 80 && !isGarbled(name)
                        && !lower.includes('profile picture') && !lower.includes('foto de perfil')) {
                        author = name;
                        break;
                    }
                }
            }
        }

        // Try to find post URL: walk up from first block and look for any link
        // that contains /posts/ or /permalink/ in href, data-href, or action attribute
        let post_url = '';
        let timestamp = '';
        if (cluster.length > 0) {
            let el = cluster[0].el;
            for (let i = 0; i < 20; i++) {
                el = el.parentElement;
                if (!el) break;
                const role = el.getAttribute && el.getAttribute('role');
                if (role === 'feed' || role === 'main') break;

                // Search for any link with post/permalink pattern
                if (!post_url) {
                    for (const a of el.querySelectorAll('a')) {
                        const href = a.getAttribute('href') || '';
                        const dataHref = a.getAttribute('data-href') || '';
                        const checkUrl = href || dataHref;
                        if (checkUrl && (checkUrl.includes('/posts/') || checkUrl.includes('/permalink/'))) {
                            if (checkUrl.startsWith('http')) {
                                post_url = checkUrl.split('?')[0];
                            } else {
                                post_url = 'https://www.facebook.com' + checkUrl.split('?')[0];
                            }
                            // Also grab aria-label as timestamp
                            const label = a.getAttribute('aria-label') || '';
                            if (label && label.length < 100) timestamp = label;
                            break;
                        }
                    }
                }

                // Also check for links that use Facebook's routing format
                // like /groups/GROUPID/posts/POSTID/
                if (!post_url) {
                    for (const a of el.querySelectorAll('a[href*="/groups/"]')) {
                        const href = a.getAttribute('href') || '';
                        const match = href.match(/\/groups\/\d+\/posts\/\d+/);
                        if (match) {
                            post_url = 'https://www.facebook.com' + match[0];
                            const label = a.getAttribute('aria-label') || '';
                            if (label && label.length < 100) timestamp = label;
                            break;
                        }
                    }
                }

                if (post_url) break;
            }
        }

        posts.push({
            text: text.substring(0, 2000),
            author,
            post_url,
            timestamp,
            reactions_count: 0,
            comments_count: 0,
        });
    }

    return posts;
}
