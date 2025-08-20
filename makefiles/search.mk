# ---- Helpers -----------------------------------------------------------------
.PHONY: help-search
help-search:
	@echo "Targets:"
	@echo "  update   				 - update candidates base"
	@echo "  queue  			  	 - create queue.txt"
	@echo "  clean        		 - clear base and queue"

# ---- Search ------------------------------------------------------------------

update:
	$(PYTHON) -m search.cli update-db --verbose

queue:
	$(PYTHON) -m search.cli build-queue

clean:
	rm -f db.sqlite queue.txt
