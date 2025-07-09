# Bienvenue, aventurier !

Ce dépôt contient un petit calculateur de drop pour Dofus Rétro, codé à la sauce Boune. Rien de bien sérieux ici : c'est surtout un terrain d'expérimentation pour le programme **Cody**.

On bidouille du Java avec JavaFX pour afficher des boutons qui brillent et des taux de drop qui font rêver. Si tu trouves un bug, c'est normal, on teste des trucs !

Tout le contenu de ce dépôt appartient au programme **Cody**. En clair : « tous les droits sont réservés », alors ne va pas piquer le code sans demander, OK ?

Amuse-toi bien et que la chance soit avec toi sur les drops !

## Tester le projet avec IntelliJ IDEA

1. Ouvrez **IntelliJ IDEA** et choisissez *Open* puis sélectionnez le fichier `pom.xml`.
   Le projet Maven sera importé automatiquement.
2. Vérifiez que le plugin **JavaFX** est installé (File → Settings → Plugins). Ensuite,
   faites un **Reload Maven Project** pour récupérer toutes les dépendances.
3. Dans la fenêtre *Maven* (à droite), développez `Plugins` → `javafx` et lancez `javafx:run`.
   L'application se lance alors via la classe `boune.DofusDropCalculator`.

Vous pouvez également créer une configuration *Application* classique en
précisant `boune.DofusDropCalculator` comme classe principale. Assurez-vous
que le JDK utilisé correspond à la version 17 définie dans le `pom.xml`.

## Générer l'archive JAR

Tout se fait via **Maven**. Depuis IntelliJ ou en ligne de commande, exécutez :

```bash
mvn clean      # nettoie le dossier target
mvn compile    # compile les sources
mvn package    # produit dofus-drop-calculator.jar dans target/
```

Le plugin *maven-shade* créera un JAR exécutable. Une fois la commande terminée,
l'archive se trouve dans `target/dofus-drop-calculator.jar`. Pour la lancer :

```bash
java -jar target/dofus-drop-calculator.jar
```

## Générer une image autonome avec jpackage

Pour créer un exécutable Windows embarquant la JRE et JavaFX :

```bash
mvn clean javafx:jlink jpackage:jpackage
```

Le résultat se trouve dans `target/installer/` et fonctionne sans Java installé.

## Lancer le JAR avec `run.bat`

Cody, pour exécuter facilement l'application depuis Windows, crée un fichier
`run.bat` dans le même dossier que `dofus-drop-calculator.jar` et copie-y le
script suivant :

```bat
@echo off
rem -----------------------------------------------------------
rem  Lance DofusDropCalculator depuis ce dossier (target)
rem -----------------------------------------------------------

:: Se place dans le répertoire où se trouve le script
pushd "%~dp0"

:: Optionnel : si JAVA_HOME est défini, on l’utilise
if exist "%JAVA_HOME%\bin\java.exe" (
    set "JAVA_CMD=%JAVA_HOME%\bin\java.exe"
) else (
    set "JAVA_CMD=java"
)

:: Exécution – on garde la console ouverte après coup
"%JAVA_CMD%" --enable-native-access=ALL-UNNAMED ^
             -jar "%~dp0dofus-drop-calculator.jar"

pause
```

Une fois le fichier enregistré, double-clique simplement sur `run.bat` pour
lancer le calculateur.

## Astuce de nettoyage

Assurez-vous de lancer la commande Maven depuis la racine du projet :

```bash
cd ..
mvn clean package
```

## Résolution du dossier `target` verrouillé

Sous Windows, `mvn clean` peut échouer si un processus garde un fichier ouvert
dans `target/`. Fermez toute fenêtre exécutant le JAR ou un test JavaFX,
puis relancez :

```powershell
mvn -U clean package
```

Le `pom.xml` configure désormais le plugin `maven-clean-plugin` avec
`failOnError=false` pour continuer le build même en cas de fichier verrouillé.
