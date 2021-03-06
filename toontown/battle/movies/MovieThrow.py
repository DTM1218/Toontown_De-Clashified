from direct.interval.IntervalGlobal import *

import MovieCamera
import MovieUtil
from MovieUtil import calcAvgSuitPos
from toontown.battle.BattleBase import *
from toontown.battle.movies.BattleProps import *
from toontown.battle.movies.BattleSounds import *
from toontown.suit.SuitDNA import *
from toontown.toon.ToonDNA import *

notify = DirectNotifyGlobal.directNotify.newCategory('MovieThrow')
hitSoundFiles = ('AA_tart_only.ogg', 'AA_slice_only.ogg',
                 'AA_slice_only.ogg', 'AA_slice_only.ogg',
                 'AA_wholepie_only.ogg', 'AA_throw_cream_pie_cog.ogg',
                 'AA_throw_wedding_cake_cog.ogg', 'AA_throw_wedding_cake_cog.ogg')
tPieLeavesHand = 2.7
tPieHitsSuit = 3.0
tSuitDodges = 2.45
ratioMissToHit = 1.5
tPieShrink = 0.7
pieFlyTaskName = 'MovieThrow-pieFly'


def addHit(suitDict, suitId, hitCount):
    if suitId in suitDict:
        suitDict[suitId] += hitCount
    else:
        suitDict[suitId] = hitCount


def doThrows(throws):
    if len(throws) == 0:
        return None, None
    suitThrowsDict = {}
    for throw in throws:
        if attackAffectsGroup(throw['track'], throw['level']):
            pass
        else:
            suitId = throw['target']['suit'].doId
            if suitId in suitThrowsDict:
                suitThrowsDict[suitId].append(throw)
            else:
                suitThrowsDict[suitId] = [throw]

    suitThrows = MovieUtil.sortAttacks(suitThrowsDict)
    totalHitDict = {}
    singleHitDict = {}
    groupHitDict = {}
    
    for throw in throws:
        if attackAffectsGroup(throw['track'], throw['level']):
            for i in xrange(len(throw['target'])):
                target = throw['target'][i]
                suitId = target['suit'].doId
                if target['hp'] > 0:
                    addHit(groupHitDict, suitId, 1)
                    addHit(totalHitDict, suitId, 1)
                else:
                    addHit(groupHitDict, suitId, 0)
                    addHit(totalHitDict, suitId, 0)

        else:
            suitId = throw['target']['suit'].doId
            if throw['target']['hp'] > 0:
                addHit(singleHitDict, suitId, 1)
                addHit(totalHitDict, suitId, 1)
            else:
                addHit(singleHitDict, suitId, 0)
                addHit(totalHitDict, suitId, 0)

    notify.debug('singleHitDict = %s' % singleHitDict)
    notify.debug('groupHitDict = %s' % groupHitDict)
    notify.debug('totalHitDict = %s' % totalHitDict)
    delay = 0.0
    mainTrack = Parallel()
    for suitThrow in suitThrows:
        if len(suitThrow) > 0:
            throwFunct = __doSuitThrows(suitThrow)
            if throwFunct:
                mainTrack.append(Sequence(Wait(delay), throwFunct))
            delay = delay + TOON_THROW_SUIT_DELAY

    retTrack = Sequence()
    retTrack.append(mainTrack)
    groupThrowIntervals = Parallel()
    groupThrows = []
    for throw in throws:
        if attackAffectsGroup(throw['track'], throw['level']):
            groupThrows.append(throw)

    for throw in groupThrows:
        tracks = __throwGroupPie(throw, 0, groupHitDict)
        if tracks:
            for track in tracks:
                groupThrowIntervals.append(track)

    retTrack.append(groupThrowIntervals)
    camDuration = retTrack.getDuration()
    camTrack = MovieCamera.chooseThrowShot(throws, suitThrowsDict, camDuration)
    return retTrack, camTrack


def __doSuitThrows(throws):
    toonTracks = Parallel()
    delay = 0.0
    hitCount = 0
    for throw in throws:
        if throw['target']['hp'] > 0:
            hitCount += 1
        else:
            break

    for throw in throws:
        tracks = __throwPie(throw, delay, hitCount)
        if tracks:
            for track in tracks:
                toonTracks.append(track)

        delay = delay + TOON_THROW_DELAY

    return toonTracks


def __showProp(prop, parent, pos):
    prop.reparentTo(parent)
    prop.setPos(pos)


def __animProp(props, propName, propType):
    if 'actor' == propType:
        for prop in props:
            prop.play(propName)

    elif 'model' == propType:
        pass
    else:
        notify.error('No such propType as: %s' % propType)


def __billboardProp(prop):
    scale = prop.getScale()
    prop.setBillboardPointWorld()
    prop.setScale(scale)


def __suitMissPoint(suit, other=render):
    pnt = suit.getPos(other)
    pnt.setZ(pnt[2] + suit.getHeight() * 1.3)
    return pnt


def __propPreflight(props, suit, toon, battle):
    prop = props[0]
    toon.update(0)
    prop.wrtReparentTo(battle)
    props[1].reparentTo(hidden)
    for ci in xrange(prop.getNumChildren()):
        prop.getChild(ci).setHpr(0, -90, 0)

    targetPnt = MovieUtil.avatarFacePoint(suit, other=battle)
    prop.lookAt(targetPnt)


def __propPreflightGroup(props, suits, toon, battle):
    prop = props[0]
    toon.update(0)
    prop.wrtReparentTo(battle)
    props[1].reparentTo(hidden)
    for ci in xrange(prop.getNumChildren()):
        prop.getChild(ci).setHpr(0, -90, 0)

    avgTargetPt = Point3(0, 0, 0)
    for suit in suits:
        avgTargetPt += MovieUtil.avatarFacePoint(suit, other=battle)

    avgTargetPt /= len(suits)
    prop.lookAt(avgTargetPt)


def __piePreMiss(missDict, pie, suitPoint, other=render):
    missDict['pie'] = pie
    missDict['startScale'] = pie.getScale()
    missDict['startPos'] = pie.getPos(other)
    v = Vec3(suitPoint - missDict['startPos'])
    endPos = missDict['startPos'] + v * ratioMissToHit
    missDict['endPos'] = endPos


def __pieMissLerpCallback(t, missDict):
    pie = missDict['pie']
    newPos = missDict['startPos'] * (1.0 - t) + missDict['endPos'] * t
    if t < tPieShrink:
        tScale = 0.0001
    else:
        tScale = (t - tPieShrink) / (1.0 - tPieShrink)
    newScale = missDict['startScale'] * max(1.0 - tScale, 0.01)
    pie.setPos(newPos)
    pie.setScale(newScale)


def __piePreMissGroup(missDict, pies, suitPoint, other=render):
    missDict['pies'] = pies
    missDict['startScale'] = pies[0].getScale()
    missDict['startPos'] = pies[0].getPos(other)
    v = Vec3(suitPoint - missDict['startPos'])
    endPos = missDict['startPos'] + v * ratioMissToHit
    missDict['endPos'] = endPos
    notify.debug('startPos=%s' % missDict['startPos'])
    notify.debug('v=%s' % v)
    notify.debug('endPos=%s' % missDict['endPos'])


def __pieMissGroupLerpCallback(t, missDict):
    pies = missDict['pies']
    newPos = missDict['startPos'] * (1.0 - t) + missDict['endPos'] * t
    if t < tPieShrink:
        tScale = 0.0001
    else:
        tScale = (t - tPieShrink) / (1.0 - tPieShrink)
    newScale = missDict['startScale'] * max(1.0 - tScale, 0.01)
    for pie in pies:
        pie.setPos(newPos)
        pie.setScale(newScale)


def __getWeddingCakeSoundTrack(hitSuit, node=None):
    throwTrack = Sequence()
    if hitSuit:
        throwSound = globalBattleSoundCache.getSound('AA_throw_wedding_cake.ogg')
        songTrack = Sequence()
        songTrack.append(Wait(1.0))
        songTrack.append(SoundInterval(throwSound, node=node))
        splatSound = globalBattleSoundCache.getSound('AA_throw_wedding_cake_cog.ogg')
        splatTrack = Sequence()
        splatTrack.append(Wait(tPieHitsSuit))
        splatTrack.append(SoundInterval(splatSound, node=node))
        throwTrack.append(Parallel(songTrack, splatTrack))
    else:
        throwSound = globalBattleSoundCache.getSound('AA_throw_wedding_cake_miss.ogg')
        throwTrack.append(Wait(tSuitDodges))
        throwTrack.append(SoundInterval(throwSound, node=node))
    return throwTrack


def __getSoundTrack(level, hitSuit, node=None):
    if level == WEDDING_LEVEL_INDEX:
        return __getWeddingCakeSoundTrack(hitSuit, node)
    throwSound = globalBattleSoundCache.getSound('AA_pie_throw_only.ogg')
    throwTrack = Sequence(Wait(2.6), SoundInterval(throwSound, node=node))
    if hitSuit:
        hitSound = globalBattleSoundCache.getSound(hitSoundFiles[level])
        hitTrack = Sequence(Wait(tPieLeavesHand), SoundInterval(hitSound, node=node))
        return Parallel(throwTrack, hitTrack)
    else:
        return throwTrack


def __throwPie(throw, delay, hitCount):
    toon = throw['toon']
    target = throw['target']
    suit = target['suit']
    hp = target['hp']
    hpBonus = target['hpBonus']
    kbBonus = target['kbBonus']
    sidestep = throw['sidestep']
    died = target['died']
    revived = target['revived']
    leftSuits = target['leftSuits']
    rightSuits = target['rightSuits']
    level = throw['level']
    battle = throw['battle']
    suitPos = suit.getPos(battle)
    origHpr = toon.getHpr(battle)
    notify.debug('toon: %s throws tart at suit: %d for hp: %d died: %d' % (toon.getName(), suit.doId, hp, died))
    pieName = pieNames[level]
    hitSuit = hp > 0
    pie = globalPropPool.getProp(pieName)
    pieType = globalPropPool.getPropType(pieName)
    pie2 = MovieUtil.copyProp(pie)
    pies = [pie, pie2]
    hands = toon.getRightHands()
    splatName = 'splat-' + pieName
    if pieName == 'wedding-cake':
        splatName = 'splat-birthday-cake'
    splat = globalPropPool.getProp(splatName)
    toonTrack = toonThrowTrack(toon, battle, delay, suitPos, origHpr)
    pieShow = Func(MovieUtil.showProps, pies, hands)
    pieAnim = Func(__animProp, pies, pieName, pieType)
    pieScale1 = LerpScaleInterval(pie, 1.0, pie.getScale(), startScale=MovieUtil.PNT3_NEARZERO)
    pieScale2 = LerpScaleInterval(pie2, 1.0, pie2.getScale(), startScale=MovieUtil.PNT3_NEARZERO)
    pieScale = Parallel(pieScale1, pieScale2)
    piePreflight = Func(__propPreflight, pies, suit, toon, battle)
    pieTrack = Sequence(Wait(delay), pieShow, pieAnim, pieScale, Func(battle.movie.needRestoreRenderProp, pies[0]),
                        Wait(tPieLeavesHand - 1.0), piePreflight)
    soundTrack = __getSoundTrack(level, hitSuit, toon)
    if hitSuit:
        pieFly = LerpPosInterval(pie, tPieHitsSuit - tPieLeavesHand, pos=MovieUtil.avatarFacePoint(suit, other=battle),
                                 name=pieFlyTaskName, other=battle)
        pieHide = Func(MovieUtil.removeProps, pies)
        splatShow = Func(__showProp, splat, suit, Point3(0, 0, suit.getHeight()))
        splatBillboard = Func(__billboardProp, splat)
        splatAnim = ActorInterval(splat, splatName)
        splatHide = Func(MovieUtil.removeProp, splat)
        pieTrack.append(pieFly)
        pieTrack.append(pieHide)
        pieTrack.append(Func(battle.movie.clearRenderProp, pies[0]))
        pieTrack.append(splatShow)
        pieTrack.append(splatBillboard)
        pieTrack.append(splatAnim)
        pieTrack.append(splatHide)
    else:
        missDict = {}
        if sidestep:
            suitPoint = MovieUtil.avatarFacePoint(suit, other=battle)
        else:
            suitPoint = __suitMissPoint(suit, other=battle)
        piePreMiss = Func(__piePreMiss, missDict, pie, suitPoint, battle)
        pieMiss = LerpFunctionInterval(__pieMissLerpCallback, extraArgs=[missDict],
                                       duration=(tPieHitsSuit - tPieLeavesHand) * ratioMissToHit)
        pieHide = Func(MovieUtil.removeProps, pies)
        pieTrack.append(piePreMiss)
        pieTrack.append(pieMiss)
        pieTrack.append(pieHide)
        pieTrack.append(Func(battle.movie.clearRenderProp, pies[0]))
    if hitSuit:
        suitResponseTrack = Sequence()
        showDamage = Func(suit.showHpText, -hp, openEnded=0, attackTrack=THROW_TRACK)
        updateHealthBar = Func(suit.updateHealthBar, hp)
        if kbBonus > 0:
            anim = 'pie-small-react'
            suitInterval = MovieUtil.startSuitKnockbackInterval(suit, anim, battle)
        elif hitCount == 1:
            suitInterval = Parallel(ActorInterval(suit, 'pie-small-react'),
                                    MovieUtil.createSuitStunInterval(suit, 0.3, 1.3))
        else:
            suitInterval = ActorInterval(suit, 'pie-small-react')
        suitResponseTrack.append(Wait(delay + tPieHitsSuit))
        suitResponseTrack.append(showDamage)
        suitResponseTrack.append(updateHealthBar)
        suitResponseTrack.append(suitInterval)
        bonusTrack = Sequence(Wait(delay + tPieHitsSuit))
        if kbBonus > 0:
            bonusTrack.append(Wait(0.75))
            bonusTrack.append(updateHealthBar)
            bonusTrack.append(Func(suit.showHpText, -kbBonus, 2, openEnded=0, attackTrack=THROW_TRACK))
            bonusTrack.append(updateHealthBar)
        if hpBonus > 0:
            bonusTrack.append(Wait(0.75))
            bonusTrack.append(Func(suit.showHpText, -hpBonus, 1, openEnded=0, attackTrack=THROW_TRACK))
            bonusTrack.append(updateHealthBar)
        if revived != 0:
            suitResponseTrack.append(MovieUtil.createSuitReviveTrack(suit, battle))
        elif died != 0:
            suitResponseTrack.append(MovieUtil.createSuitDeathTrack(suit, battle))
        else:
            suitResponseTrack.append(Func(suit.loop, 'neutral'))
        suitResponseTrack = Parallel(suitResponseTrack, bonusTrack)
    else:
        suitResponseTrack = MovieUtil.createSuitDodgeMultitrack(delay + tSuitDodges, suit, leftSuits, rightSuits)
    if not hitSuit and delay > 0:
        return [toonTrack, soundTrack, pieTrack]
    else:
        return [toonTrack,
                soundTrack,
                pieTrack,
                suitResponseTrack]


def __createWeddingCakeFlight(throw, pie, pies):
    battle = throw['battle']
    level = throw['level']
    sidestep = throw['sidestep']
    numTargets = len(throw['target'])
    pieName = pieNames[level]
    splatName = 'splat-' + pieName
    if pieName == 'wedding-cake':
        splatName = 'splat-birthday-cake'
    splat = globalPropPool.getProp(splatName)
    splats = [splat]
    for i in xrange(numTargets - 1):
        splats.append(MovieUtil.copyProp(splat))

    cakePartStrs = ['cake1', 'cake2', 'cake3', 'caketop']
    cakeParts = []
    for part in cakePartStrs:
        cakeParts.append(pie.find('**/%s' % part))

    cakePartDivisions = {1: [[cakeParts[0], cakeParts[1], cakeParts[2], cakeParts[3]]],
                         2: [[cakeParts[0], cakeParts[1]], [cakeParts[2], cakeParts[3]]],
                         3: [[cakeParts[0], cakeParts[1]], [cakeParts[2]], [cakeParts[3]]],
                         4: [[cakeParts[0]], [cakeParts[1]], [cakeParts[2]], [cakeParts[3]]]}
    cakePartDivToUse = cakePartDivisions[len(throw['target'])]
    groupPieTracks = Parallel()
    for i in xrange(numTargets):
        target = throw['target'][i]
        suit = target['suit']
        hitSuit = target['hp'] > 0
        singlePieTrack = Sequence()
        if hitSuit:
            piePartReParent = Func(changeCakePartParent, pie, cakePartDivToUse[i])
            singlePieTrack.append(piePartReParent)
            cakePartTrack = Parallel()
            for cakePart in cakePartDivToUse[i]:
                pieFly = LerpPosInterval(cakePart, tPieHitsSuit - tPieLeavesHand,
                                         pos=MovieUtil.avatarFacePoint(suit, other=battle), name=pieFlyTaskName,
                                         other=battle)
                cakePartTrack.append(pieFly)

            singlePieTrack.append(cakePartTrack)
            pieRemoveCakeParts = Func(MovieUtil.removeProps, cakePartDivToUse[i])
            pieHide = Func(MovieUtil.removeProps, pies)
            splatShow = Func(__showProp, splats[i], suit, Point3(0, 0, suit.getHeight()))
            splatBillboard = Func(__billboardProp, splats[i])
            splatAnim = ActorInterval(splats[i], splatName)
            splatHide = Func(MovieUtil.removeProp, splats[i])
            singlePieTrack.append(pieRemoveCakeParts)
            singlePieTrack.append(pieHide)
            singlePieTrack.append(Func(battle.movie.clearRenderProp, pies[0]))
            singlePieTrack.append(splatShow)
            singlePieTrack.append(splatBillboard)
            singlePieTrack.append(splatAnim)
            singlePieTrack.append(splatHide)
        else:
            missDict = {}
            if sidestep:
                suitPoint = MovieUtil.avatarFacePoint(suit, other=battle)
            else:
                suitPoint = __suitMissPoint(suit, other=battle)
            piePartReParent = Func(changeCakePartParent, pie, cakePartDivToUse[i])
            piePreMiss = Func(__piePreMissGroup, missDict, cakePartDivToUse[i], suitPoint, battle)
            pieMiss = LerpFunctionInterval(__pieMissGroupLerpCallback, extraArgs=[missDict],
                                           duration=(tPieHitsSuit - tPieLeavesHand) * ratioMissToHit)
            pieHide = Func(MovieUtil.removeProps, pies)
            pieRemoveCakeParts = Func(MovieUtil.removeProps, cakePartDivToUse[i])
            singlePieTrack.append(piePartReParent)
            singlePieTrack.append(piePreMiss)
            singlePieTrack.append(pieMiss)
            singlePieTrack.append(pieRemoveCakeParts)
            singlePieTrack.append(pieHide)
            singlePieTrack.append(Func(battle.movie.clearRenderProp, pies[0]))
        groupPieTracks.append(singlePieTrack)

    return groupPieTracks


def __throwGroupPie(throw, delay, groupHitDict):
    toon = throw['toon']
    battle = throw['battle']
    level = throw['level']
    numTargets = len(throw['target'])
    avgSuitPos = calcAvgSuitPos(throw)
    origHpr = toon.getHpr(battle)
    toonTrack = toonThrowTrack(toon, battle, delay, avgSuitPos, origHpr)
    suits = []
    for i in xrange(numTargets):
        suits.append(throw['target'][i]['suit'])

    pieName = pieNames[level]
    pie = globalPropPool.getProp(pieName)
    pieType = globalPropPool.getPropType(pieName)
    pie2 = MovieUtil.copyProp(pie)
    pies = [pie, pie2]
    hands = toon.getRightHands()
    pieShow = Func(MovieUtil.showProps, pies, hands)
    pieAnim = Func(__animProp, pies, pieName, pieType)
    pieScale1 = LerpScaleInterval(pie, 1.0, pie.getScale() * 1.5, startScale=MovieUtil.PNT3_NEARZERO)
    pieScale2 = LerpScaleInterval(pie2, 1.0, pie2.getScale() * 1.5, startScale=MovieUtil.PNT3_NEARZERO)
    pieScale = Parallel(pieScale1, pieScale2)
    piePreflight = Func(__propPreflightGroup, pies, suits, toon, battle)
    pieTrack = Sequence(Wait(delay), pieShow, pieAnim, pieScale, Func(battle.movie.needRestoreRenderProp, pies[0]),
                        Wait(tPieLeavesHand - 1.0), piePreflight)
    if level == WEDDING_LEVEL_INDEX:
        groupPieTracks = __createWeddingCakeFlight(throw, pie, pies)
    else:
        notify.error('unhandled throw level %d' % level)
    pieTrack.append(groupPieTracks)
    didThrowHitAnyone = False
    for i in xrange(numTargets):
        target = throw['target'][i]
        hitSuit = target['hp'] > 0
        if hitSuit:
            didThrowHitAnyone = True

    soundTrack = __getSoundTrack(level, didThrowHitAnyone, toon)
    groupSuitResponseTrack = Parallel()
    for i in xrange(numTargets):
        target = throw['target'][i]
        suit = target['suit']
        hitSuit = target['hp'] > 0
        leftSuits = target['leftSuits']
        rightSuits = target['rightSuits']
        hp = target['hp']
        kbBonus = target['kbBonus']
        hpBonus = target['hpBonus']
        died = target['died']
        revived = target['revived']
        if hitSuit:
            singleSuitResponseTrack = Sequence()
            showDamage = Func(suit.showHpText, -hp, openEnded=0, attackTrack=THROW_TRACK)
            updateHealthBar = Func(suit.updateHealthBar, hp)
            if kbBonus > 0:
                anim = 'pie-small-react'
                suitInterval = MovieUtil.startSuitKnockbackInterval(suit, anim, battle)
            elif groupHitDict[suit.doId] == 1:
                suitInterval = Parallel(ActorInterval(suit, 'pie-small-react'),
                                        MovieUtil.createSuitStunInterval(suit, 0.3, 1.3))
            else:
                suitInterval = ActorInterval(suit, 'pie-small-react')
            singleSuitResponseTrack.append(Wait(delay + tPieHitsSuit))
            singleSuitResponseTrack.append(showDamage)
            singleSuitResponseTrack.append(updateHealthBar)
            singleSuitResponseTrack.append(suitInterval)
            bonusTrack = Sequence(Wait(delay + tPieHitsSuit))
            if kbBonus > 0:
                bonusTrack.append(Wait(0.75))
                bonusTrack.append(Func(suit.showHpText, -kbBonus, 2, openEnded=0, attackTrack=THROW_TRACK))
            if hpBonus > 0:
                bonusTrack.append(Wait(0.75))
                bonusTrack.append(Func(suit.showHpText, -hpBonus, 1, openEnded=0, attackTrack=THROW_TRACK))
            if revived != 0:
                singleSuitResponseTrack.append(MovieUtil.createSuitReviveTrack(suit, battle))
            elif died != 0:
                singleSuitResponseTrack.append(MovieUtil.createSuitDeathTrack(suit, battle))
            else:
                singleSuitResponseTrack.append(Func(suit.loop, 'neutral'))
            singleSuitResponseTrack = Parallel(singleSuitResponseTrack, bonusTrack)
        else:
            groupHitValues = groupHitDict.values()
            if groupHitValues.count(0) == len(groupHitValues):
                singleSuitResponseTrack = MovieUtil.createSuitDodgeMultitrack(delay + tSuitDodges, suit, leftSuits,
                                                                              rightSuits)
            else:
                singleSuitResponseTrack = Sequence(Wait(tPieHitsSuit - 0.1), Func(MovieUtil.indicateMissed, suit, 1.0))
        groupSuitResponseTrack.append(singleSuitResponseTrack)

    return [toonTrack,
            pieTrack,
            soundTrack,
            groupSuitResponseTrack]


def toonThrowTrack(toon, battle, delay, suitPos, origHpr):
    return Sequence(Wait(delay), Func(toon.headsUp, battle, suitPos), ActorInterval(toon, 'throw'),
                    Func(toon.loop, 'neutral'), Func(toon.setHpr, battle, origHpr))


def changeCakePartParent(pie, cakeParts):
    pieParent = pie.getParent()
    notify.debug('pieParent = %s' % pieParent)
    for cakePart in cakeParts:
        cakePart.wrtReparentTo(pieParent)
