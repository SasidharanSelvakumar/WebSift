import httpx

if __name__ == "__main__":
    client = httpx.Client(timeout=30.0)

    for test_url, test_mode in [
        ("https://httpbin.org/html", "main"),
        ("https://example.com", "full"),
    ]:
        print(f"\n==========================================")
        print(f"Testing URL: {test_url} (Mode: {test_mode})")
        print(f"==========================================")
        try:
            res = client.post("http://127.0.0.1:8000/api/extract", json={"url": test_url, "mode": test_mode})
            print("Status:", res.status_code)
            data = res.json()
            print("Success:", data.get("success"))
            print("Title:", data.get("page_title"))
            stats = data.get("stats", {})
            print(f"Stats: Blocks={stats.get('block_count')}, Words={stats.get('word_count')}, Headings={stats.get('headings_count')}, Paragraphs={stats.get('paragraphs_count')}")
            
            for item in data.get("items", [])[:4]:
                seq = item["sequence_number"]
                ctype = item["content_type"]
                text = item["text_content"][:70]
                heading = item.get("heading")
                print(f"  [{seq}] ({ctype}) Heading='{heading}': {text}...")

            # Export tests
            csv_res = client.post("http://127.0.0.1:8000/api/export/csv", json={
                "items": data["items"],
                "source_url": data["source_url"],
                "page_title": data["page_title"]
            })
            print(f"CSV Generated: {csv_res.headers.get('content-disposition')} ({len(csv_res.content)} bytes)")

            txt_res = client.post("http://127.0.0.1:8000/api/export/txt", json={
                "items": data["items"],
                "source_url": data["source_url"],
                "page_title": data["page_title"],
                "mode": data["mode"]
            })
            print(f"TXT Generated: {txt_res.headers.get('content-disposition')} ({len(txt_res.content)} bytes)")
        except Exception as e:
            print("Could not connect to live server:", e)

