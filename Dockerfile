FROM curator-base

USER root

COPY requirements-extra.txt /app/requirements-extra.txt
RUN pip install --no-cache-dir -r /app/requirements-extra.txt

COPY --chown=runner:runner main.py /app/main.py
COPY --chown=runner:runner curator/ /app/curator/
COPY --chown=runner:runner agents/ /app/agents/

USER runner

ENTRYPOINT ["python", "/app/main.py"]
CMD ["--help"]
